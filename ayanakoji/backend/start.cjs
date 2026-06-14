const { spawn } = require('child_process');
const path = require('path');

const proc = spawn(
  path.join(__dirname, '.venv/bin/uvicorn'),
  ['app.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
  { cwd: __dirname, stdio: 'inherit' }
);

proc.on('close', (code) => process.exit(code));
