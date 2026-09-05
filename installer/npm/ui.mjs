/** Terminal presentation only: no installation, account access, or progress guesses. */

const RESET = '\u001b[0m';
const CLEAR_LINE = '\r\u001b[2K';
const SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const POSITIVE = new Set(['verified', 'installed', 'configured', 'ready', 'success', 'complete', 'completed']);
const NEGATIVE = new Set(['failed', 'error']);
const ACTIVE = new Set(['running', 'checking']);
const COLORS = {
  brand: [82, 214, 220], muted: [146, 156, 179], good: [108, 219, 174],
  warning: [240, 190, 110], bad: [247, 126, 142], text: [215, 222, 239],
};

function sanitize(value, limit = 4096) {
  const raw = typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
    ? String(value).slice(0, limit) : '';
  return raw
    // Strip complete and unterminated OSC/DCS/APC/PM/SOS sequences, including C1 forms.
    .replace(/(?:\u001b\]|\u009d)[\s\S]*?(?:\u0007|\u001b\\|\u009c|$)/g, '')
    .replace(/(?:\u001b[P_^X]|[\u0090\u0098\u009e\u009f])[\s\S]*?(?:\u001b\\|\u009c|$)/g, '')
    .replace(/(?:\u001b\[|\u009b)[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\u001b[ -/]*[@-~]/g, '')
    .replace(/[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/g, '')
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ')
    .replace(/\s+/g, ' ').trim();
}

function cellWidth(character) {
  if (/\p{Mark}/u.test(character)) return 0;
  const code = character.codePointAt(0);
  return code >= 0x1100 && (
    code <= 0x115f || code === 0x2329 || code === 0x232a ||
    (code >= 0x2e80 && code <= 0xa4cf && code !== 0x303f) ||
    (code >= 0xac00 && code <= 0xd7a3) || (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xfe10 && code <= 0xfe19) || (code >= 0xfe30 && code <= 0xfe6f) ||
    (code >= 0xff00 && code <= 0xff60) || (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff) || (code >= 0x20000 && code <= 0x3fffd)
  ) ? 2 : 1;
}

function fit(value, width) {
  const characters = Array.from(value);
  if (characters.reduce((sum, character) => sum + cellWidth(character), 0) <= width) return value;
  const suffix = '.'.repeat(Math.min(3, width));
  let used = 0;
  let result = '';
  for (const character of characters) {
    const size = cellWidth(character);
    if (used + size > width - suffix.length) break;
    result += character;
    used += size;
  }
  return result + suffix;
}

function statusOf(value) {
  return sanitize(value, 80).toLowerCase().replace(/[ _]+/g, '-') || 'unknown';
}

function statusColor(status) {
  if (NEGATIVE.has(status)) return 'bad';
  if (status === 'blocked' || status === 'warning' || status === 'not-configured') return 'warning';
  return POSITIVE.has(status) ? 'good' : 'muted';
}

function disabled(value) {
  return value !== undefined && value !== '' && value !== '0' && value !== 'false';
}

export function createUI({ stdout = process.stdout, stderr = process.stderr, env = process.env } = {}) {
  const plain = Object.hasOwn(env, 'NO_COLOR') || env.FORCE_COLOR === '0'
    || disabled(env.CI) || env.TERM === 'dumb';
  const colored = (stream) => stream?.isTTY === true && !plain;
  const animationDisabled = Object.hasOwn(env, 'STATION_NO_ANIMATION')
    && env.STATION_NO_ANIMATION !== '0' && env.STATION_NO_ANIMATION !== 'false';
  const animate = colored(stdout) && !animationDisabled;
  let closed = false;
  let timer;
  let active;
  let frame = 0;

  function width(stream) {
    return stream?.isTTY === true && Number.isFinite(stream.columns) && stream.columns > 0
      ? Math.min(120, Math.floor(stream.columns)) : 100;
  }

  function paint(text, color, stream = stdout) {
    return colored(stream) ? `\u001b[38;2;${COLORS[color].join(';')}m${text}${RESET}` : text;
  }

  function write(stream, text) {
    if (closed) return false;
    try {
      return stream.write(text) !== false;
    } catch {
      // Presentation failure must not leave a timer running or mask an install error.
      closed = true;
      clearInterval(timer);
      timer = undefined;
      active = undefined;
      return false;
    }
  }

  function line(text = '', color = 'text', stream = stdout) {
    const visible = stream?.isTTY === true ? fit(text, width(stream)) : text;
    return write(stream, paint(visible, color, stream) + '\n');
  }

  function wrapped(text, color = 'text') {
    if (stdout?.isTTY !== true) return line(text, color);
    const columns = width(stdout);
    let row = '';
    let used = 0;
    for (const character of text) {
      const size = cellWidth(character);
      if (used + size > columns && row) {
        line(row, color);
        row = '';
        used = 0;
      }
      row += size > columns ? '?' : character;
      used += Math.min(size, columns);
    }
    line(row, color);
  }

  function rail(item, symbol, stream = stdout) {
    const status = statusOf(item.status);
    const phase = sanitize(item.phase, 240) || 'install';
    const message = sanitize(item.message);
    const text = `${symbol} [${status.toUpperCase()}] ${phase}${message ? ` — ${message}` : ''}`;
    // Leave one cell free so animation cannot auto-wrap to a second row.
    return paint(stream?.isTTY === true ? fit(text, Math.max(1, width(stream) - 1)) : text,
      statusColor(status), stream);
  }

  function finishActive() {
    clearInterval(timer);
    timer = undefined;
    if (!active || closed) return;
    // No cursor is hidden and no global signal handler is installed. A caller's
    // finally { ui.close(); } restores a clean line without changing exit policy.
    const item = active;
    active = undefined;
    write(stdout, CLEAR_LINE + rail(item, '│') + '\n');
  }

  function banner() {
    if (closed) return;
    finishActive();
    const columns = width(stdout);
    const title = columns < 38 ? ['AGENTIK', 'STATION'] : ['A G E N T I K  /  S T A T I O N'];
    line();
    for (const row of title) {
      const text = fit(row, columns);
      if (colored(stdout)) {
        const chars = Array.from(text);
        const gradient = chars.map((character, index) => {
          const ratio = index / Math.max(1, chars.length - 1);
          const rgb = [82 + 97 * ratio, 214 - 73 * ratio, 220 + 30 * ratio].map(Math.round);
          return `\u001b[38;2;${rgb.join(';')}m${character}`;
        }).join('');
        write(stdout, gradient + RESET + '\n');
      } else {
        line(row);
      }
    }
    line('Chief AI Officer installer', 'muted');
    line((colored(stdout) ? '─' : '-').repeat(Math.min(columns, 56)), 'muted');
  }

  function plan(planObject = {}) {
    if (closed) return;
    finishActive();
    line('INSTALLATION PLAN', 'brand');
    for (const [label, value] of [
      ['Mode', planObject.mode], ['Root', planObject.root],
      ['Platform', [sanitize(planObject.platform), sanitize(planObject.arch)].filter(Boolean).join(' / ')],
      ['Profile', planObject.profile],
    ]) {
      wrapped(`${label}: ${sanitize(value) || 'not specified'}`);
    }
    const steps = Array.isArray(planObject.steps) ? planObject.steps : [];
    if (!steps.length) line('No installation steps declared.', 'muted');
    for (const [index, step] of steps.slice(0, 100).entries()) {
      wrapped(`${String(index + 1).padStart(2, '0')}  ${sanitize(step) || 'unnamed step'}`, 'muted');
    }
    if (steps.length > 100) line(`${steps.length - 100} additional steps omitted.`, 'warning');
    const warnings = Array.isArray(planObject.warnings) ? planObject.warnings : [];
    for (const warning of warnings.slice(0, 100)) wrapped(`! ${sanitize(warning)}`, 'warning');
    line('Plan only. No step is marked complete.', 'muted');
  }

  function event(item = {}) {
    if (closed) return;
    finishActive();
    const status = statusOf(item.status);
    const entry = { phase: sanitize(item.phase, 240), status, message: sanitize(item.message) };
    if (animate && ACTIVE.has(status)) {
      active = entry;
      frame = 0;
      if (!write(stdout, rail(entry, SPINNER[frame]))) return;
      timer = setInterval(() => {
        if (closed || !active) return;
        frame = (frame + 1) % SPINNER.length;
        if (!write(stdout, CLEAR_LINE + rail(active, SPINNER[frame]))) {
          clearInterval(timer);
          timer = undefined;
        }
      }, 90);
      timer.unref();
      return;
    }
    const stream = NEGATIVE.has(status) || status === 'blocked' ? stderr : stdout;
    write(stream, rail(entry, colored(stream) ? '│' : '-', stream) + '\n');
  }

  function summary(report = {}) {
    if (closed) return;
    finishActive();
    const checks = Array.isArray(report.checks) ? report.checks : [];
    let status = statusOf(report.status);
    // Do not print a successful headline above evidence that explicitly failed.
    if (checks.some((check) => NEGATIVE.has(statusOf(check?.status)))) status = 'failed';
    else if (POSITIVE.has(status) && checks.some((check) => statusOf(check?.status) === 'blocked')) status = 'blocked';
    line();
    line(`RESULT / ${status.toUpperCase()}`, statusColor(status));
    for (const check of checks.slice(0, 100)) {
      const checkStatus = statusOf(check?.status);
      line(`[${checkStatus.toUpperCase()}] ${sanitize(check?.id, 240) || 'check'}`, statusColor(checkStatus));
      if (check?.detail) wrapped(`  ${sanitize(check.detail)}`, 'muted');
    }
    if (checks.length > 100) line(`${checks.length - 100} additional checks omitted. See the receipt.`, 'warning');
    if (report.receipt) wrapped(`Receipt: ${sanitize(report.receipt)}`, 'muted');
    const next = Array.isArray(report.next) ? report.next : [];
    if (next.length) {
      line('NEXT', 'brand');
      for (const [index, step] of next.slice(0, 100).entries()) wrapped(`${index + 1}. ${sanitize(step)}`);
    }
    line('Readiness reflects only the checks shown.', 'muted');
  }

  function close() {
    if (closed) return;
    finishActive();
    closed = true;
  }

  return { banner, plan, event, summary, close };
}
