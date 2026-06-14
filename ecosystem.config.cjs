module.exports = {
  apps: [
    {
      name: 'ayanakoji-frontend-3000',
      cwd: './ayanakoji/frontend',
      script: 'node_modules/.bin/next',
      args: 'dev',
      interpreter: 'node',
      env: { NODE_ENV: 'development', PORT: '3000' },
    },
    {
      name: 'ayanakoji-backend-8000',
      cwd: './ayanakoji/backend',
      script: 'start.cjs',
      interpreter: 'node',
      env: { PYTHONUNBUFFERED: '1' },
    },
  ],
}
