/**
 * Geo Intel Monitor — Apps Script companion.
 *
 * SETUP:
 *  1. In Google Apps Script (script.google.com), create a new project,
 *     paste this file in as Code.gs.
 *  2. Go to Project Settings (gear icon) > Script Properties and add
 *     the REQUIRED rows:
 *       RENDER_BASE_URL   -> https://your-app-name.onrender.com
 *       TRIGGER_SECRET    -> (same value as TRIGGER_SECRET in Render)
 *       EMAIL_TO          -> yourgmail@gmail.com (comma-separate for
 *                             multiple recipients)
 *
 *     Optional — customize the schedule (any you skip use the default
 *     shown; times are 24-hour "HH:MM" in your script's timezone):
 *       DIGEST_TIME_1              -> default 10:00
 *       DIGEST_TIME_2              -> default 22:00
 *       WEEKLY_DAY                 -> default MONDAY (MONDAY..SUNDAY)
 *       WEEKLY_TIME                -> default 09:00
 *       ARCHIVE_DAY_OF_MONTH       -> default 1
 *       ARCHIVE_TIME               -> default 03:00
 *       KEEPALIVE_INTERVAL_MIN     -> default 10
 *       COLLECT_INTERVAL_MIN       -> default 30
 *       CRITICAL_CHECK_INTERVAL_MIN -> default 30
 *
 *  3. Run setupTriggers() once (function dropdown > setupTriggers >
 *     Run) and approve the permissions it asks for.
 *  4. To CHANGE a time later: update the Script Property's value, then
 *     run setupTriggers() again (safe to re-run — it always rebuilds
 *     the triggers from scratch using current property values).
 */

function _props() {
  return PropertiesService.getScriptProperties();
}

// Reads a "HH:MM" Script Property, falls back to a default if unset/invalid.
function _readTime(propName, defaultHHMM) {
  const raw = _props().getProperty(propName) || defaultHHMM;
  const parts = raw.split(':');
  const hour = parseInt(parts[0], 10);
  const minute = parseInt(parts[1], 10);
  if (isNaN(hour) || isNaN(minute)) {
    Logger.log(`Invalid time in ${propName}="${raw}", using default ${defaultHHMM}`);
    const d = defaultHHMM.split(':');
    return { hour: parseInt(d[0], 10), minute: parseInt(d[1], 10) };
  }
  return { hour, minute };
}

function _readInt(propName, defaultVal) {
  const raw = _props().getProperty(propName);
  const n = parseInt(raw, 10);
  return isNaN(n) ? defaultVal : n;
}

function _readWeekDay(propName, defaultDay) {
  const raw = (_props().getProperty(propName) || defaultDay).toUpperCase();
  return ScriptApp.WeekDay[raw] || ScriptApp.WeekDay[defaultDay];
}

function _renderUrl(path) {
  const base = _props().getProperty('RENDER_BASE_URL');
  const key = _props().getProperty('TRIGGER_SECRET');
  const sep = path.indexOf('?') === -1 ? '?' : '&';
  return base + path + sep + 'key=' + encodeURIComponent(key);
}

/** Cheap ping, just to stop the free Render instance from sleeping. */
function keepAlive() {
  try {
    UrlFetchApp.fetch(_renderUrl('/health'), { muteHttpExceptions: true });
  } catch (e) {
    Logger.log('keepAlive failed: ' + e);
  }
}

/** The actual collection job — heavier, so runs less often than keepAlive. */
function runCollect() {
  try {
    UrlFetchApp.fetch(_renderUrl('/collect'), {
      method: 'post',
      muteHttpExceptions: true,
    });
  } catch (e) {
    Logger.log('runCollect failed: ' + e);
  }
}

/** Fetches the digest from Render and emails it via Gmail. Runs at 10:00 & 22:00. */
function sendDigest() {
  const emailTo = _props().getProperty('EMAIL_TO');
  const resp = UrlFetchApp.fetch(_renderUrl('/digest-data'), {
    method: 'get',
    muteHttpExceptions: true,
  });

  if (resp.getResponseCode() !== 200) {
    Logger.log('digest-data fetch failed: ' + resp.getContentText('UTF-8'));
    return;
  }

  // Explicit UTF-8 decode — without this, emoji and other multi-byte
  // characters in the digest get corrupted into "������" garbage text.
  const data = JSON.parse(resp.getContentText('UTF-8'));
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'dd MMM yyyy HH:mm');
  const subject = '🌍 Geo Intel Brief — ' + today +
      (data.critical_count > 0 ? '  ⚠️ ' + data.critical_count + ' CRITICAL' : '');

  GmailApp.sendEmail(emailTo, subject, 'This email requires HTML support.', {
    htmlBody: data.html,
  });
}

/** Checks for CRITICAL items and sends an instant alert if found. Runs every 30 min. */
function checkCritical() {
  try {
    UrlFetchApp.fetch(_renderUrl('/critical'), {
      method: 'post',
      muteHttpExceptions: true,
    });
  } catch (e) {
    Logger.log('checkCritical failed: ' + e);
  }
}

/** Sends the weekly trend report. Runs Monday morning. */
function sendWeekly() {
  try {
    UrlFetchApp.fetch(_renderUrl('/weekly'), {
      method: 'post',
      muteHttpExceptions: true,
    });
  } catch (e) {
    Logger.log('sendWeekly failed: ' + e);
  }
}

/** Archives old articles to Telegram + purges them from MongoDB. Runs monthly. */
function archiveOld() {
  try {
    UrlFetchApp.fetch(_renderUrl('/archive-old'), {
      method: 'post',
      muteHttpExceptions: true,
    });
  } catch (e) {
    Logger.log('archiveOld failed: ' + e);
  }
}

/** Run this once by hand to install every timer. Safe to re-run. */
function setupTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  const keepAliveMin = _readInt('KEEPALIVE_INTERVAL_MIN', 10);
  const collectMin = _readInt('COLLECT_INTERVAL_MIN', 30);
  const criticalMin = _readInt('CRITICAL_CHECK_INTERVAL_MIN', 30);
  const morning = _readTime('DIGEST_TIME_1', '10:00');
  const evening = _readTime('DIGEST_TIME_2', '22:00');
  const weeklyDay = _readWeekDay('WEEKLY_DAY', 'MONDAY');
  const weeklyTime = _readTime('WEEKLY_TIME', '09:00');
  const archiveDay = _readInt('ARCHIVE_DAY_OF_MONTH', 1);
  const archiveTime = _readTime('ARCHIVE_TIME', '03:00');

  // 1. Keep Render awake — light ping.
  ScriptApp.newTrigger('keepAlive').timeBased().everyMinutes(keepAliveMin).create();

  // 2. Actual collection job.
  ScriptApp.newTrigger('runCollect').timeBased().everyMinutes(collectMin).create();

  // 3. Morning digest.
  ScriptApp.newTrigger('sendDigest').timeBased()
      .atHour(morning.hour).nearMinute(morning.minute).everyDays(1).create();

  // 4. Evening digest.
  ScriptApp.newTrigger('sendDigest').timeBased()
      .atHour(evening.hour).nearMinute(evening.minute).everyDays(1).create();

  // 5. Critical alert check.
  ScriptApp.newTrigger('checkCritical').timeBased().everyMinutes(criticalMin).create();

  // 6. Weekly report.
  ScriptApp.newTrigger('sendWeekly').timeBased()
      .onWeekDay(weeklyDay).atHour(weeklyTime.hour).nearMinute(weeklyTime.minute).create();

  // 7. Archive old articles to Telegram.
  ScriptApp.newTrigger('archiveOld').timeBased()
      .onMonthDay(archiveDay).atHour(archiveTime.hour).nearMinute(archiveTime.minute).create();

  Logger.log(`Triggers installed: keep-alive/${keepAliveMin}min, collect/${collectMin}min, ` +
      `critical-check/${criticalMin}min, digests at ${morning.hour}:${morning.minute} & ` +
      `${evening.hour}:${evening.minute}, weekly on day ${weeklyDay} at ${weeklyTime.hour}:${weeklyTime.minute}, ` +
      `archive monthly on day ${archiveDay} at ${archiveTime.hour}:${archiveTime.minute}.`);
}
