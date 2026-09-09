/**
 * Geo Intel Monitor — Apps Script companion.
 *
 * Jobs:
 *  1. Ping /health every ~10 min — cheap, just keeps the free Render
 *     instance awake. Does NOT run collection (that would be wasteful
 *     this often).
 *  2. Trigger /collect every 30 min — the actual (heavier) collection
 *     job. Less frequent than the keep-alive ping since collecting
 *     continuously is what "24/7" means here, not collecting every
 *     few minutes.
 *  3. At 10:00 and 22:00 — fetch the digest and email it via Gmail
 *     (avoids Render's SMTP issues). This is the twice-daily summary.
 *  4. Every 30 min — check for CRITICAL items and send an instant
 *     alert if any are found.
 *  5. Weekly, Monday morning — send the weekly trend report.
 *
 * SETUP:
 *  1. In Google Apps Script (script.google.com), create a new project,
 *     paste this file in as Code.gs.
 *  2. Go to Project Settings (gear icon) > Script Properties and add
 *     THREE rows (Property name -> Value, don't mix these up):
 *       RENDER_BASE_URL   -> https://your-app-name.onrender.com
 *       TRIGGER_SECRET    -> (same value as TRIGGER_SECRET in Render)
 *       EMAIL_TO          -> yourgmail@gmail.com (comma-separate for
 *                             multiple recipients)
 *  3. Run setupTriggers() once (function dropdown > setupTriggers >
 *     Run) and approve the permissions it asks for. That installs all
 *     the timers below automatically.
 */

function _props() {
  return PropertiesService.getScriptProperties();
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
    Logger.log('digest-data fetch failed: ' + resp.getContentText());
    return;
  }

  const data = JSON.parse(resp.getContentText());
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

/** Run this once by hand to install every timer. Safe to re-run. */
function setupTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // 1. Keep Render awake — light ping, every 10 min.
  ScriptApp.newTrigger('keepAlive')
      .timeBased()
      .everyMinutes(10)
      .create();

  // 2. Actual collection — every 30 min (24/7, just not every few minutes).
  ScriptApp.newTrigger('runCollect')
      .timeBased()
      .everyMinutes(30)
      .create();

  // 3. Morning digest, 10:00.
  ScriptApp.newTrigger('sendDigest')
      .timeBased()
      .atHour(10)
      .nearMinute(0)
      .everyDays(1)
      .create();

  // 4. Evening digest, 22:00 (12 hours after the morning one).
  ScriptApp.newTrigger('sendDigest')
      .timeBased()
      .atHour(22)
      .nearMinute(0)
      .everyDays(1)
      .create();

  // 5. Critical alert check — every 30 min.
  ScriptApp.newTrigger('checkCritical')
      .timeBased()
      .everyMinutes(30)
      .create();

  // 6. Weekly report — Monday, 9:00.
  ScriptApp.newTrigger('sendWeekly')
      .timeBased()
      .onWeekDay(ScriptApp.WeekDay.MONDAY)
      .atHour(9)
      .nearMinute(0)
      .create();

  Logger.log('Triggers installed: keep-alive/10min, collect/30min, ' +
      'critical-check/30min, digests at 10:00 & 22:00, weekly Monday 9:00.');
}
