/**
 * Geo Intel Monitor — Apps Script companion.
 *
 * Two jobs:
 *  1. Ping Render every ~10-14 min so the free-tier instance stays awake
 *     and keeps collecting continuously.
 *  2. At 10:00 and 22:00, fetch the digest HTML from Render and send it
 *     via your own Gmail account (GmailApp) — this avoids Render's free
 *     tier SMTP failures entirely.
 *
 * SETUP:
 *  1. In Google Apps Script (script.google.com), create a new project,
 *     paste this file in as Code.gs.
 *  2. Go to Project Settings > Script Properties and add:
 *       RENDER_BASE_URL   = https://your-app-name.onrender.com
 *       TRIGGER_SECRET    = (same value as TRIGGER_SECRET in Render's .env)
 *       EMAIL_TO          = yourgmail@gmail.com   (where the digest goes)
 *  3. Run setupTriggers() once (Run menu > select function > setupTriggers)
 *     and approve the permissions it asks for. That installs the 3 timers
 *     below automatically — you don't need to add them by hand.
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

/** Keeps the free Render instance awake + collecting. Runs every ~12 min. */
function keepAliveAndCollect() {
  try {
    UrlFetchApp.fetch(_renderUrl('/collect'), {
      method: 'post',
      muteHttpExceptions: true,
    });
  } catch (e) {
    Logger.log('keepAliveAndCollect failed: ' + e);
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

/** Optional: instant critical alert check, e.g. every 30 min. */
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

/** Run this once by hand to install all the timers. */
function setupTriggers() {
  // Clear any old triggers from this script first, so re-running is safe.
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // Keep-alive + continuous collection, every 12 minutes.
  ScriptApp.newTrigger('keepAliveAndCollect')
      .timeBased()
      .everyMinutes(12)
      .create();

  // Morning digest at 10:00.
  ScriptApp.newTrigger('sendDigest')
      .timeBased()
      .atHour(10)
      .nearMinute(0)
      .everyDays(1)
      .create();

  // Evening digest at 22:00.
  ScriptApp.newTrigger('sendDigest')
      .timeBased()
      .atHour(22)
      .nearMinute(0)
      .everyDays(1)
      .create();

  Logger.log('Triggers installed: keep-alive every 12 min, digests at 10:00 and 22:00.');
}
