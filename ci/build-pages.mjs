import { cp, mkdir, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = join(root, 'build', 'pages');
const frontend = join(root, 'web', 'dist');
const backend = join(root, 'backend');
const compatibilityDate = '2026-11-14';

if (!(await stat(join(frontend, 'index.html'))).size) {
    throw new Error('前端产物缺失，请先在 web/ 执行 npm run build。');
}

// 只清理本脚本固定的产物目录，避免旧文件混入新部署。
if (output !== resolve(root, 'build', 'pages')) {
    throw new Error('部署产物路径无效。');
}
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(frontend, output, { recursive: true });

const result = spawnSync(process.execPath, [
    join(backend, 'node_modules', 'wrangler', 'bin', 'wrangler.js'),
    'pages', 'functions', 'build', 'functions',
    '--outdir', join(output, '_worker.js'),
    '--minify', '--compatibility-date', compatibilityDate,
], { cwd: backend, stdio: 'inherit', env: { ...process.env, WRANGLER_SEND_METRICS: 'false' } });
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);

const workerFiles = await readdir(join(output, '_worker.js'));
if (!workerFiles.some(name => name.endsWith('.js'))) {
    throw new Error('Pages Functions 未生成 Worker 模块。');
}
await writeFile(join(output, '_routes.json'), JSON.stringify({
    version: 1,
    include: ['/*'],
    exclude: ['/css/*', '/entry/*', '/fonts/*', '/img/*', '/js/*', '/static/*', '/favicon.ico'],
}, null, 2) + '\n');

// 将源码提交保存在静态产物中，供线上发布核对。
const revision = process.env.GITHUB_SHA || spawnSync('git', ['rev-parse', 'HEAD'], {
    cwd: root, encoding: 'utf8',
}).stdout?.trim();
if (!/^[0-9a-f]{40}$/.test(revision ?? '')) throw new Error('无法确定构建源码提交。');
await writeFile(join(output, 'deployment.json'), JSON.stringify({ revision }) + '\n');
console.log(`Pages 部署包已生成：${output}`);
