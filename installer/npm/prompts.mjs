import readline from 'node:readline/promises';
import { Writable } from 'node:stream';

export function terminalPrompts(input = process.stdin, output = process.stdout) {
  if (!input.isTTY || !output.isTTY) return false;
  return {
    async prompt({ message, secret = false, defaultValue = '' }) {
      // A muted readline terminal handles editing/paste without echoing secrets.
      const sink = secret ? new Writable({ write(_chunk, _encoding, callback) { callback(); } }) : output;
      if (secret) { sink.isTTY = true; sink.columns = output.columns; output.write(`${message} (hidden): `); }
      const rl = readline.createInterface({ input, output: sink, terminal: true });
      try {
        const result = await rl.question(secret ? '' : `${message}${defaultValue ? ` [${defaultValue}]` : ''}: `);
        return result || defaultValue;
      } finally { rl.close(); if (secret) output.write('\n'); }
    },
    async confirm({ message }) { return /^(yes|y)$/i.test((await this.prompt({ message: `${message} [y/N]` })).trim()); },
  };
}
