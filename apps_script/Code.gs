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
 *     Optional — customize the schedule. SET THESE YOURSELF, however you
 *     like — nothing is hardcoded to 10:00/22:00 anymore:
 *       DIGEST_TIMES               -> comma-separated "HH:MM" list, e.g.
 *                                      "08:00,13:30,20:00" — as many as
 *                                      you want, any times you want.
 *                                      Default if unset: "10:00,22:00".
 *                                      IGNORED if DIGEST_INTERVAL_HOURS is set.
 *       DIGEST_INTERVAL_HOURS       -> send the digest every N hours instead
 *                                      of at fixed clock times, e.g. "1" for
 *                                      hourly. Allowed values: 1, 2, 4, 6, 8,
 *                                      12 (Apps Script's own restriction on
 *                                      hourly triggers). Uses ONE trigger
 *                                      instead of one-per-time, so this is
 *                                      the right way to do "every hour" --
 *                                      listing 24 DIGEST_TIMES entries would
 *                                      blow past Apps Script's 20-triggersper-project limit once combined with keepAlive/runCollect/etc. Unset
 *                                      by default -- DIGEST_TIMES is used
 *                                      unless you set this.
 *       WEEKLY_DAY                 -> default MONDAY (MONDAY..SUNDAY)
 *       WEEKLY_TIME                -> default 09:00
 *       CLEANUP_DAY_OF_MONTH       -> default 1
 *       CLEANUP_TIME                -> default 03:00
 *       KEEPALIVE_INTERVAL_MIN     -> default 10
 *       COLLECT_INTERVAL_MIN       -> default 30
 *       CRITICAL_CHECK_INTERVAL_MIN -> default 30
 *
 *  3. Run setupTriggers() once (function dropdown > setupTriggers >
 *     Run) and approve the permissions it asks for.
 *  4. To CHANGE any time later: update the Script Property's value, then
 *     run setupTriggers() again (safe to re-run — it always rebuilds
 *     the triggers from scratch using current property values). This is
 *     the only step needed to change your schedule yourself, any time.
 *
 * DASHBOARD AS AN APPS SCRIPT WEB PAGE (optional):
 *  If you'd rather open your dashboard at a script.google.com URL instead
 *  of remembering your Render URL, deploy this same project as a Web App:
 *    Deploy > New deployment > select type "Web app" >
 *    Execute as: Me > Who has access: Only myself (or "Anyone with the
 *    link" if you want to share it) > Deploy.
 *  Copy the Web App URL it gives you and open it in a browser — doGet()
 *  below fetches your Render dashboard and serves it through that URL.
 */

function _props() {
  return PropertiesService.getScriptProperties();
}

// Reads a "HH:MM" Script Property, falls back to a default if unset/invalid.
function _parseTime(raw) {
  const parts = raw.split(':');
  const hour = parseInt(parts[0], 10);
  const minute = parseInt(parts[1], 10);
  if (isNaN(hour) || isNaN(minute)) return null;
  return { hour, minute };
}

// Reads DIGEST_TIMES as a comma-separated list, e.g. "08:00,13:30,20:00".
// You control exactly how many times and which ones — no fixed count.
function _readDigestTimes() {
  const raw = _props().getProperty('DIGEST_TIMES') || '10:00,22:00';
  const times = raw.split(',').map(s => s.trim()).filter(Boolean).map(_parseTime).filter(Boolean);
  return times.length ? times : [{ hour: 10, minute: 0 }, { hour: 22, minute: 0 }];
}

function _readTime(propName, defaultHHMM) {
  const raw = _props().getProperty(propName) || defaultHHMM;
  return _parseTime(raw) || _parseTime(defaultHHMM);
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

/** The actual collection job — heavier, so runs less often than keepAlive.
 * This is also when full records get backed up to Telegram, if
 * ENABLE_TELEGRAM_BACKUP=true in Render's environment variables. */
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

/** Fetches the digest from Render and emails it via Gmail. Runs at every
 * time listed in DIGEST_TIMES. */
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

  // At an hourly (or otherwise frequent) cadence, most cycles will have
  // nothing new. Skip sending an empty "No items this cycle" email rather
  // than filling the inbox — only skip if there's also nothing critical to
  // flag. Remove this block if you'd rather always get a "still nothing new"
  // email as a heartbeat.
  if ((!data.article_ids || data.article_ids.length === 0) && !(data.critical_count > 0)) {
    Logger.log('sendDigest: nothing new this cycle, skipped sending.');
    return;
  }

  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'dd MMM yyyy HH:mm');
  const subject = '🌍 Geo Intel Brief — ' + today +
      (data.critical_count > 0 ? '  ⚠️ ' + data.critical_count + ' CRITICAL' : '');

  GmailApp.sendEmail(emailTo, subject, 'This email requires HTML support.', {
    htmlBody: data.html,
  });

  // Only tell Render to mark these articles as "sent" AFTER the Gmail send
  // above didn't throw. If this step is skipped (e.g. quota error), the
  // same articles just get included again in the next digest instead of
  // silently vanishing.
  if (data.article_ids && data.article_ids.length) {
    try {
      UrlFetchApp.fetch(_renderUrl('/mark-emailed'), {
        method: 'post',
        contentType: 'application/json',
        payload: JSON.stringify({ article_ids: data.article_ids }),
        muteHttpExceptions: true,
      });
    } catch (e) {
      Logger.log('mark-emailed failed (articles will just repeat next digest): ' + e);
    }
  }
}

/** Checks for CRITICAL items and sends an instant alert if found. Runs every
 * CRITICAL_CHECK_INTERVAL_MIN minutes. */
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

/** Sends the weekly trend report. Runs on WEEKLY_DAY at WEEKLY_TIME. */
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

/** Deletes MongoDB metadata older than METADATA_CLEANUP_AFTER_DAYS (set in
 * Render's environment variables). Nothing is lost — full records already
 * live permanently in the Telegram backup channel from collection time.
 * Runs monthly on CLEANUP_DAY_OF_MONTH. */
function cleanupOld() {
  try {
    UrlFetchApp.fetch(_renderUrl('/cleanup-old'), {
      method: 'post',
      muteHttpExceptions: true,
    });
  } catch (e) {
    Logger.log('cleanupOld failed: ' + e);
  }
}

/** Run this once by hand to install every timer. Safe to re-run — always
 * rebuilds triggers from the current Script Property values, so changing
 * a schedule is just: edit the property, run this again. */
function setupTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  const keepAliveMin = _readInt('KEEPALIVE_INTERVAL_MIN', 10);
  const collectMin = _readInt('COLLECT_INTERVAL_MIN', 30);
  const criticalMin = _readInt('CRITICAL_CHECK_INTERVAL_MIN', 30);
  const digestIntervalHours = _readInt('DIGEST_INTERVAL_HOURS', 0); // 0 = unset -> use DIGEST_TIMES instead
  const digestTimes = _readDigestTimes();
  const weeklyDay = _readWeekDay('WEEKLY_DAY', 'MONDAY');
  const weeklyTime = _readTime('WEEKLY_TIME', '09:00');
  const cleanupDay = _readInt('CLEANUP_DAY_OF_MONTH', 1);
  const cleanupTime = _readTime('CLEANUP_TIME', '03:00');

  // 1. Keep Render awake — light ping.
  ScriptApp.newTrigger('keepAlive').timeBased().everyMinutes(keepAliveMin).create();

  // 2. Actual collection job (this is also when Telegram backup happens).
  ScriptApp.newTrigger('runCollect').timeBased().everyMinutes(collectMin).create();

  // 3. Digest email(s). Two mutually exclusive modes:
  //    - DIGEST_INTERVAL_HOURS set -> ONE recurring trigger, e.g. every 1
  //      hour. This is the correct way to do "hourly digests" -- it uses a
  //      single trigger no matter the frequency, instead of one trigger per
  //      clock time (which would blow past Apps Script's 20-trigger limit
  //      for anything more than a handful of times).
  //    - otherwise -> one trigger per entry in DIGEST_TIMES, at those exact
  //      clock times, same as before.
  let digestScheduleDesc;
  if (digestIntervalHours > 0) {
    ScriptApp.newTrigger('sendDigest').timeBased().everyHours(digestIntervalHours).create();
    digestScheduleDesc = `every ${digestIntervalHours}h (DIGEST_INTERVAL_HOURS)`;
  } else {
    digestTimes.forEach(t => {
      ScriptApp.newTrigger('sendDigest').timeBased()
          .atHour(t.hour).nearMinute(t.minute).everyDays(1).create();
    });
    digestScheduleDesc = `at [${digestTimes.map(t => `${t.hour}:${('0'+t.minute).slice(-2)}`).join(', ')}] (DIGEST_TIMES)`;
  }

  // 4. Critical alert check.
  ScriptApp.newTrigger('checkCritical').timeBased().everyMinutes(criticalMin).create();

  // 5. Weekly report.
  ScriptApp.newTrigger('sendWeekly').timeBased()
      .onWeekDay(weeklyDay).atHour(weeklyTime.hour).nearMinute(weeklyTime.minute).create();

  // 6. Monthly MongoDB metadata cleanup (Telegram backup is unaffected).
  ScriptApp.newTrigger('cleanupOld').timeBased()
      .onMonthDay(cleanupDay).atHour(cleanupTime.hour).nearMinute(cleanupTime.minute).create();

  Logger.log(`Triggers installed: keep-alive/${keepAliveMin}min, collect/${collectMin}min, ` +
      `critical-check/${criticalMin}min, digests ${digestScheduleDesc}, ` +
      `weekly on day ${weeklyDay} at ${weeklyTime.hour}:${weeklyTime.minute}, ` +
      `cleanup monthly on day ${cleanupDay} at ${cleanupTime.hour}:${cleanupTime.minute}.`);
}

/**
 * Serves your Render dashboard through this Apps Script's own Web App URL,
 * so you have a script.google.com link for it instead of only the Render
 * URL. Requires deploying this project as a Web App (see setup notes at
 * the top of this file). Just proxies/fetches — all the actual data still
 * comes from Render/MongoDB/Telegram; this changes nothing about the data.
 */
function doGet(e) {
  const resp = UrlFetchApp.fetch(_renderUrl('/dashboard'), { muteHttpExceptions: true });
  if (resp.getResponseCode() !== 200) {
    return HtmlService.createHtmlOutput(
      '<p>Could not load dashboard from Render (HTTP ' + resp.getResponseCode() + '). ' +
      'Check RENDER_BASE_URL and TRIGGER_SECRET in Script Properties.</p>'
    );
  }
  return HtmlService.createHtmlOutput(resp.getContentText('UTF-8'))
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
