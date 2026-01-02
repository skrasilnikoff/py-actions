import time
from typing import List, Optional
from datetime import datetime, timezone

from bs4 import BeautifulSoup
import os
import smtplib
from email.message import EmailMessage
import json
import hashlib
import subprocess
import asyncio
from telegram_notification import send_telegram_notification


URL = "https://www.dtek-dnem.com.ua/ua/shutdowns"

# Values per your spec (now configurable via env)
CITY = os.environ.get("CITY", "")
STREET = os.environ.get("STREET", "")
HOUSE_NUM = os.environ.get("HOUSE_NUM", "")

# Fallback to env_vars.json if not in environment
if not CITY or not STREET or not HOUSE_NUM:
    try:
        with open("env_vars.json", "r") as f:
            env_vars = json.load(f)
        CITY = CITY or env_vars.get("CITY", "")
        STREET = STREET or env_vars.get("STREET", "")
        HOUSE_NUM = HOUSE_NUM or env_vars.get("HOUSE_NUM", "")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

# Hardcoded SMTP defaults (user must still provide SMTP_USER, SMTP_PASS, SMTP_FROM)
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
DEFAULT_SMTP_USE_SSL = True
DEFAULT_SMTP_STARTTLS = False
DEFAULT_STATE_FILE = os.environ.get("STATE_FILE", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")


def parse_fact_table_to_slots(table_html: str) -> Optional[List[str]]:
	"""Parse a rendered fact table into 48 half-hour slots.

	Slot values: 'on', 'off', 'maybe', 'unknown'.
	"""
	soup = BeautifulSoup(table_html, "html.parser")
	table = soup.find("table")
	if not table:
		return None

	tbody = table.find("tbody")
	if not tbody:
		return None

	tr = tbody.find("tr", class_="current-day") or tbody.find("tr")
	if not tr:
		return None

	tds = tr.find_all("td")
	# Day name cells usually have colspan; hour cells do not.
	hour_tds = [td for td in tds if not td.has_attr("colspan")]
	if not hour_tds:
		return None

	slots: List[str] = []
	for td in hour_tds[:24]:
		classes = td.get("class") or []
		cls = " ".join(classes)
		if "cell-scheduled" in cls:
			slots.extend(["off", "off"])
		elif "cell-non-scheduled" in cls:
			slots.extend(["on", "on"])
		elif "cell-first-half" in cls:
			slots.extend(["off", "on"])
		elif "cell-second-half" in cls:
			slots.extend(["on", "off"])
		elif "cell-scheduled-maybe" in cls:
			slots.extend(["maybe", "maybe"])
		else:
			slots.extend(["unknown", "unknown"])

	while len(slots) < 48:
		slots.append("unknown")
	return slots[:48]


def slots_to_ranges(slots: List[str], status: str) -> List[str]:
	ranges: List[str] = []
	i = 0
	n = len(slots)
	while i < n:
		if slots[i] == status:
			start = i
			while i < n and slots[i] == status:
				i += 1
			end = i

			sh, sm = divmod(start, 2)
			eh, em = divmod(end, 2)
			start_time = f"{sh:02d}:{'00' if sm == 0 else '30'}"
			end_time = f"{eh:02d}:{'00' if em == 0 else '30'}"
			ranges.append(f"{start_time} - {end_time}")
		else:
			i += 1
	return ranges


def selenium_get_fact_table_html() -> str:
	from selenium import webdriver
	from selenium.webdriver.common.by import By
	from selenium.webdriver.common.keys import Keys
	from selenium.webdriver.support.ui import WebDriverWait
	from selenium.webdriver.support import expected_conditions as EC
	from selenium.webdriver.chrome.service import Service
	from selenium.common.exceptions import ElementNotInteractableException
	from webdriver_manager.chrome import ChromeDriverManager

	options = webdriver.ChromeOptions()
	options.add_argument("--headless=new")
	options.add_argument("--no-sandbox")
	options.add_argument("--disable-dev-shm-usage")
	# Force a wide viewport so the site renders the full-hour table layout
	options.add_argument("--window-size=1400,900")

	driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
	try:
		# Ensure window size is applied in headless mode
		driver.set_window_size(1400, 900)
	except Exception:
		pass
	try:
		driver.get(URL)

		# Per spec: wait 5 seconds after opening the page
		time.sleep(5)

		wait = WebDriverWait(driver, 60)

		def dismiss_blocking_modal() -> None:
			"""Close/remove first-load modal that can intercept clicks."""
			# Try a few different strategies. If none work, we fall back to JS remove.
			try:
				# Wait briefly to see if modal is present
				modal_present = driver.execute_script(
					"return !!document.querySelector('.modal__container[aria-modal=" + '"true"' + "]') || !!document.querySelector('.modal__container--firstPopup') || !!document.querySelector('.m-attention__container');"
				)
			except Exception:
				modal_present = False

			if not modal_present:
				return

			# 1) Click common close buttons
			close_selectors = [
				".modal__container [data-modal-close]",
				".modal__container .modal__close",
				".modal__container .close",
				".modal__container button[aria-label='Close']",
				".modal__container button",
			]
			for sel in close_selectors:
				try:
					btn = driver.find_element(By.CSS_SELECTOR, sel)
					driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
					btn.click()
					time.sleep(0.3)
					# If modal gone, stop
					gone = driver.execute_script(
						"return !document.querySelector('.modal__container[aria-modal=" + '"true"' + "]') && !document.querySelector('.modal__container--firstPopup') && !document.querySelector('.m-attention__container');"
					)
					if gone:
						return
				except Exception:
					pass

			# 2) Press Escape
			try:
				body = driver.find_element(By.TAG_NAME, "body")
				body.send_keys(Keys.ESCAPE)
				time.sleep(0.3)
				gone = driver.execute_script(
					"return !document.querySelector('.modal__container[aria-modal=" + '"true"' + "]') && !document.querySelector('.modal__container--firstPopup') && !document.querySelector('.m-attention__container');"
				)
				if gone:
					return
			except Exception:
				pass

			# 3) Force-remove modal + backdrops (last resort)
			try:
				driver.execute_script(
					"""
					for (const sel of ['.modal__container[aria-modal="true"]', '.modal__container--firstPopup', '.m-attention__container']) {
						const el = document.querySelector(sel);
						if (el) el.remove();
					}
					// remove common backdrops/locks
					for (const sel of ['.modal__overlay', '.modal__backdrop', '.ps__rail-x', '.ps__rail-y']) {
						const els = document.querySelectorAll(sel);
						els.forEach(e => e.remove());
					}
					document.documentElement.style.overflow = 'auto';
					document.body.style.overflow = 'auto';
					"""
				)
				time.sleep(0.2)
			except Exception:
				pass

		# Dismiss modal (if it appears)
		dismiss_blocking_modal()

		def pick_autocomplete_exact(input_id: str, value: str) -> None:
			print(f"Selecting {input_id} -> {value}")
			# Always re-fetch an enabled element (DOM may change after selection)
			def enabled_visible(d):
				el = d.find_element(By.ID, input_id)
				return el if el.is_displayed() and el.is_enabled() else False
			inp = wait.until(enabled_visible)
			# Ensure any modal isn't intercepting clicks
			dismiss_blocking_modal()
			driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
			wait.until(EC.element_to_be_clickable((By.ID, input_id)))

			# Type using WebElement send_keys to mimic real user input
			try:
				inp.click()
			except Exception:
				pass
			try:
				inp.send_keys(Keys.COMMAND, 'a')
				inp.send_keys(Keys.BACKSPACE)
			except Exception:
				pass
			try:
				inp.send_keys(value)
			except ElementNotInteractableException:
				# Some states report enabled but still block typing; use JS input event.
				driver.execute_script(
					"arguments[0].focus(); arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
					inp,
					value,
				)

			# Find and click an item from this input's autocomplete list
			deadline = time.time() + 25
			picked = False
			last_error = None
			while time.time() < deadline and not picked:
				try:
					input_el = driver.find_element(By.ID, input_id)
					wrap = input_el.find_element(By.XPATH, "ancestor::div[contains(@class,'autocomplete')]")
					# Some UIs only show suggestions after clicking the dropdown icon
					try:
						items_wrap = wrap.find_element(By.CSS_SELECTOR, ".autocomplete-items")
						items = items_wrap.find_elements(By.CSS_SELECTOR, "div")
					except Exception:
						items = []

					if not items:
						try:
							icon = wrap.find_element(By.CSS_SELECTOR, "img")
							icon.click()
						except Exception:
							pass
						time.sleep(0.3)
						continue

					target = value.strip().lower()
					# exact match first
					for it in items:
						t = (it.text or '').strip().lower()
						if t == target:
							it.click()
							picked = True
							break
					if picked:
						break
					# contains fallback
					for it in items:
						t = (it.text or '').strip().lower()
						if target in t:
							it.click()
							picked = True
							break
					if picked:
						break
					items[0].click()
					picked = True
					break
				except Exception as e:
					last_error = e
					time.sleep(0.3)

			if not picked:
				# Dump wrapper HTML for debugging
				try:
					wrap_html = driver.execute_script(
						"const inp = document.getElementById(arguments[0]); const w = inp && inp.closest('.autocomplete'); return w ? w.outerHTML : null;",
						input_id,
					)
				except Exception:
					wrap_html = None
				if wrap_html:
					with open(f"dtek_autocomplete_{input_id}.html", "w", encoding="utf-8") as f:
						f.write(wrap_html)
				raise RuntimeError(f"Autocomplete suggestions not selectable for {input_id}: {last_error}")
			# Some flows rely on change/blur events after selecting from list
			try:
				driver.execute_script(
					"arguments[0].dispatchEvent(new Event('change', {bubbles:true})); arguments[0].blur();",
					inp,
				)
			except Exception:
				pass
			try:
				final_val = inp.get_attribute('value')
			except Exception:
				final_val = None
			print(f"Selected {input_id} (value now: {final_val!r})")

		# Fill fields strictly in order
		pick_autocomplete_exact("city", CITY)
		# Diagnostics + nudge: some versions require an explicit street-list load
		try:
			city_state = driver.execute_script(
				"const el = document.getElementById('city'); if (!el) return null; return {value: el.value, className: el.className};"
			)
			# print('City state after pick:', city_state)
		except Exception:
			pass
		try:
			driver.execute_script(
				"if (typeof DisconSchedule !== 'undefined' && DisconSchedule.ajax) {"
				"  const keys = Object.keys(DisconSchedule.ajax);"
				"  for (const k of keys) {"
				"    if (k.toLowerCase().includes('street')) { try { DisconSchedule.ajax[k](); } catch(e) {} }"
				"  }"
				"}"
			)
		except Exception:
			pass
		# Give the page a moment to unlock street after city selection
		time.sleep(0.5)
		# Some sessions keep street disabled until an internal flag is set by the popup.
		# If it's still disabled, force-enable it so we can proceed with sequential filling.
		try:
			driver.execute_script(
				"const el = document.getElementById('street'); if (el) { el.disabled = false; el.removeAttribute('disabled'); }"
			)
		except Exception:
			pass
		try:
			street_state = driver.execute_script(
				"const el = document.getElementById('street'); if (!el) return null; return {disabled: !!el.disabled, className: el.className, value: el.value};"
			)
			# print('Street state after city:', street_state)
		except Exception:
			pass

		# Wait until street becomes enabled after selecting city; if stuck, try to trigger invisible load
		try:
			wait.until(lambda d: d.find_element(By.ID, "street").is_enabled())
		except Exception:
			try:
				ajax_keys = driver.execute_script(
					"return (typeof DisconSchedule !== 'undefined' && DisconSchedule.ajax) ? Object.keys(DisconSchedule.ajax) : [];"
				)
				print('DisconSchedule.ajax keys:', ajax_keys)
			except Exception:
				pass
			# Attempt to trigger street list population if the site exposes helpers
			try:
				driver.execute_script(
					"if (typeof DisconSchedule !== 'undefined' && DisconSchedule.ajax) {"
					" if (DisconSchedule.ajax.getStreetInvisibly) DisconSchedule.ajax.getStreetInvisibly();"
					" if (DisconSchedule.ajax.getStreet) DisconSchedule.ajax.getStreet();"
					" }"
				)
			except Exception:
				pass
			wait.until(lambda d: d.find_element(By.ID, "street").is_enabled())
		pick_autocomplete_exact("street", STREET)

		# Kick off async home list load if the site uses it
		try:
			driver.execute_script(
				"if (typeof DisconSchedule !== 'undefined' && DisconSchedule.ajax && DisconSchedule.ajax.getHomeNumInvisibly) DisconSchedule.ajax.getHomeNumInvisibly();"
			)
		except Exception:
			pass

		# Per spec: wait 2 seconds before house
		time.sleep(2)
		# Force-enable house input if still disabled
		try:
			driver.execute_script(
				"const el = document.getElementById('house_num'); if (el) { el.disabled = false; el.removeAttribute('disabled'); }"
			)
		except Exception:
			pass

		# Ensure house input becomes enabled before interacting
		def house_enabled(d):
			try:
				el = d.find_element(By.ID, "house_num")
				return el.is_displayed() and el.is_enabled()
			except Exception:
				return False
		wait.until(house_enabled)

		pick_autocomplete_exact("house_num", HOUSE_NUM)

		# After selecting house, trigger the site's submit that builds the table
		try:
			driver.execute_script("if (typeof DisconSchedule !== 'undefined' && DisconSchedule.ajax && DisconSchedule.ajax.formSubmit) DisconSchedule.ajax.formSubmit('getHomeNum');")
		except Exception:
			pass

		# Wait until the fact tables container appears and an active table is rendered
		wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".discon-fact-tables")))
		# Wait for an active table or at least any table to be present
		wait.until(lambda d: d.execute_script("return !!(document.querySelector('.discon-fact-tables .discon-fact-table.active') || document.querySelector('.discon-fact-tables .discon-fact-table'))"))

		# Also wait for #group-name to show something (helps ensure selection applied)
		try:
			wait.until(lambda d: d.execute_script("const g=document.getElementById('group-name'); return g && g.innerText && g.innerText.trim().length>0;"))
		except Exception:
			# not critical, continue
			pass

		# Prefer active table
		html = driver.execute_script(
			"""
			const el = document.querySelector('.discon-fact-tables .discon-fact-table.active')
					|| document.querySelector('.discon-fact-tables .discon-fact-table');
			return el ? el.outerHTML : '';
			"""
		)
		if not html:
			raise RuntimeError("Fact table not found after filling form")
		return html
	finally:
		try:
			driver.quit()
		except Exception:
			pass


def send_off_intervals_via_email(recipient: str, off_ranges: Optional[List[str]], date_str: Optional[str]) -> None:
	"""Send the "Интервалы отключения" section via email.

	Reads SMTP settings from environment variables:
	- SMTP_HOST (default: localhost)
	- SMTP_PORT (default: 25)
	- SMTP_USER, SMTP_PASS (optional)
	- SMTP_USE_SSL (if '1' uses SMTP_SSL)
	- SMTP_STARTTLS (if '1' calls starttls() before login)
	"""
	lines = ["Интервалы отключения:"]
	if off_ranges:
		for r in off_ranges:
			lines.append(f" - {r}")
	else:
		lines.append(" - Нет интервалов отключения")
	body = "\n".join(lines)

	msg = EmailMessage()
	msg.set_content(body)
	subj_date = f" {date_str}" if date_str else ""
	msg["Subject"] = f"Интервалы отключения{subj_date}"
	msg["From"] = os.environ.get("SMTP_FROM", f"no-reply@{os.uname().nodename}")
	msg["To"] = recipient

	# Use hardcoded defaults for host/port/ssl/starttls; only credentials/from are required
	host = DEFAULT_SMTP_HOST
	port = DEFAULT_SMTP_PORT
	user = os.environ.get("SMTP_USER")
	passwd = os.environ.get("SMTP_PASS")
	use_ssl = DEFAULT_SMTP_USE_SSL
	starttls = DEFAULT_SMTP_STARTTLS

	if use_ssl:
		srv = smtplib.SMTP_SSL(host, port, timeout=30)
	else:
		srv = smtplib.SMTP(host, port, timeout=30)

	with srv:
		srv.ehlo()
		if starttls and not use_ssl:
			srv.starttls()
			srv.ehlo()
		if user:
			srv.login(user, passwd or "")
		srv.send_message(msg)


def main() -> None:
	# Get the rendered fact table HTML via Selenium and output raw HTML
	table_html = selenium_get_fact_table_html()
	if not table_html:
		raise RuntimeError("Fact table HTML not found")

	# Save to a file for inspection and also print raw HTML to stdout
	# (Do not save or print raw HTML here; proceed to parse and display results)

	def _normalize_table(html: str) -> str:
		"""If site returned a two-column table layout, normalize it into the single-row wide table.

		This reconstructs a table with a single tbody row containing 24 hourly td cells.
		"""
		try:
			soup = BeautifulSoup(html, "html.parser")
			# if already wide (has a single table with hour cols), return as-is
			if soup.find('table') and soup.find('table').find('thead') and len(soup.find_all('th')) >= 24:
				return html

			# detect possible multi-column block
			wrap = soup.find(class_='table2col') or soup
			tables = wrap.find_all('table')
			if not tables or len(tables) < 2:
				return html

			# collect hour-cell classes from both tables; each table row has third td with class
			classes = []
			for t in tables:
				for tr in t.find_all('tr'):
					tds = tr.find_all('td')
					if len(tds) >= 3:
						cls = ' '.join(tds[2].get('class') or [])
						classes.append(cls)

			# If we didn't find 24 cells, return original
			if len(classes) < 24:
				return html

			# build new single-row table
			new_div = BeautifulSoup('', 'html.parser').new_tag('div')
			new_div['rel'] = wrap.get('rel', '')
			new_div['class'] = 'discon-fact-table active'

			table_tag = BeautifulSoup('', 'html.parser').new_tag('table')
			head = BeautifulSoup('', 'html.parser').new_tag('thead')
			tr_head = BeautifulSoup('', 'html.parser').new_tag('tr')
			th0 = BeautifulSoup('', 'html.parser').new_tag('th', colspan='2')
			th0.string = 'Часові'
			tr_head.append(th0)
			for h in range(24):
				th = BeautifulSoup('', 'html.parser').new_tag('th', scope='col')
				div = BeautifulSoup('', 'html.parser').new_tag('div')
				div.string = f"{h:02d}-{(h+1)%24:02d}"
				th.append(div)
				tr_head.append(th)
			head.append(tr_head)
			table_tag.append(head)

			tbody = BeautifulSoup('', 'html.parser').new_tag('tbody')
			tr_body = BeautifulSoup('', 'html.parser').new_tag('tr')
			td_empty = BeautifulSoup('', 'html.parser').new_tag('td', colspan='2')
			td_empty.string = '\xa0'
			tr_body.append(td_empty)
			for cls in classes[:24]:
				td = BeautifulSoup('', 'html.parser').new_tag('td')
				if cls:
					td['class'] = cls
				tr_body.append(td)
			tbody.append(tr_body)
			table_tag.append(tbody)

			new_div.append(table_tag)

			legend = wrap.find(class_='discon-fact-legend')
			if legend:
				new_div.append(legend)

			return str(new_div)
		except Exception:
			return html

	# normalize before parsing
	table_html_norm = _normalize_table(table_html)

	# Now parse classes into 48 half-hour slots and print intervals + visual table
	slots = parse_fact_table_to_slots(table_html_norm)
	if slots:
		off_ranges = slots_to_ranges(slots, "off")

		# Load previous state (md5, timestamp, version) if present
		prev_md5 = None
		prev_version = 0
		import os.path as osp
		abs_state_file = osp.abspath(DEFAULT_STATE_FILE)
		print(f"DEBUG: Looking for state file at: {abs_state_file}")
		print(f"DEBUG: File exists: {osp.exists(abs_state_file)}")
		try:
			with open(DEFAULT_STATE_FILE, 'r', encoding='utf-8') as sf:
				st = json.load(sf)
				prev_md5 = st.get('md5')
				prev_version = st.get('version', 0)  # default to 0 for old files
				print(f"DEBUG: Loaded state from {DEFAULT_STATE_FILE}: md5={prev_md5}")
		except FileNotFoundError:
			print(f"DEBUG: State file not found at {DEFAULT_STATE_FILE}")
			prev_md5 = None
			prev_version = 0
		except Exception as e:
			print(f"DEBUG: Error reading state file: {e}")
			prev_md5 = None
			prev_version = 0

		# attempt to extract date from table HTML (rel attribute is often a unix timestamp)
		soup = BeautifulSoup(table_html_norm, "html.parser")
		tbl_el = soup.find(class_='discon-fact-table') or soup.find(attrs={"rel": True})
		date_str = None
		if tbl_el:
			rel = tbl_el.get('rel') or tbl_el.get('data-rel')
			if rel:
				try:
					ts = int(rel)
					# convert UTC timestamp to local timezone-aware datetime
					date_str = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime('%Y-%m-%d')
				except Exception:
					date_str = None

		if date_str:
			print(f"\nДата: {date_str}")

		# Normalize current ranges as strings and compute md5
		off_ranges = [str(r).strip() for r in off_ranges]
		joined = "\n".join(off_ranges)
		current_md5 = hashlib.md5(joined.encode('utf-8')).hexdigest()

		print(f"DEBUG off_ranges: {off_ranges}")
		print(f"DEBUG current_md5: {current_md5!r}")
		print(f"DEBUG prev_md5: {prev_md5!r}")
		print(f"DEBUG match: {prev_md5 == current_md5}")

		print("\nИнтервалы отключения (Света НЕТ):")
		if off_ranges:
			for r in off_ranges:
				print(f" - {r}")
		else:
			print(" - Нет интервалов отключения")

		# Send only if data changed since last run
		try:
			print(f"DEBUG: prev_md5: {prev_md5!r}, current_md5: {current_md5!r}")
			if prev_md5 != current_md5:
				print("Данные изменились (md5 differ), отправляю email")
				try:
					send_off_intervals_via_email(EMAIL_RECIPIENT, off_ranges, date_str)
				except Exception as e:
					print(f"Ошибка при отправке email: {e}")
				# Send Telegram notification
				body = f"Интервалы отключения:\n" + "\n".join(f" - {r}" for r in off_ranges or ["Нет интервалов отключения"])
				if date_str:
					body = f"{date_str}\n{body}"
				print(f"DEBUG: Sending Telegram message: {body}")
				asyncio.run(send_telegram_notification(body))
			else:
				print("Данные не изменились (md5 equal) — письмо не отправлено")
			
			# Always write state file (even if MD5 didn't change)
			print("Сохраняю состояние...")
			try:
				state_dir = os.path.dirname(DEFAULT_STATE_FILE) or '.'
				print(f"DEBUG: State dir: {state_dir}")
				print(f"DEBUG: Absolute state dir: {os.path.abspath(state_dir)}")
				os.makedirs(state_dir, exist_ok=True)
				print(f"DEBUG: Directory created/verified")
				state_data = {
					'md5': current_md5,
					'timestamp': datetime.now(timezone.utc).isoformat(),
					'version': 1,
					'data': off_ranges  # store the actual ranges for logging
				}
				abs_path = os.path.abspath(DEFAULT_STATE_FILE)
				print(f"DEBUG: Writing to absolute path: {abs_path}")
				with open(DEFAULT_STATE_FILE, 'w', encoding='utf-8') as sf:
					json.dump(state_data, sf, ensure_ascii=False, indent=2)
				print(f"Состояние сохранено в {DEFAULT_STATE_FILE}")
				print(f"DEBUG: File exists after write: {os.path.exists(DEFAULT_STATE_FILE)}")
				# Amend the last commit with the updated state file
				try:
					subprocess.run(["git", "add", DEFAULT_STATE_FILE], check=True)
					subprocess.run(["git", "commit", "--amend", "--no-edit"], check=True)
					print("Git commit amended with updated state.")
				except subprocess.CalledProcessError as e:
					print(f"Failed to amend git commit: {e}")
			except Exception as e:
				print(f"Не удалось сохранить состояние: {e}")
				import traceback
				traceback.print_exc()
		except Exception as e:
			print(f"Ошибка при обработке: {e}")
	else:
		print('\nНе удалось извлечь статусы из таблицы (парсер вернул None)')


if __name__ == "__main__":
	main()
