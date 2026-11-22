const account = process.env.CLOUDFLARE_ACCOUNT_ID;
const token = process.env.CLOUDFLARE_API_TOKEN;
const projectName = process.env.CLOUDFLARE_PAGES_PROJECT;
if (!account || !token) {
    throw new Error('请在 GitHub Actions Secrets 设置 CLOUDFLARE_ACCOUNT_ID 和 CLOUDFLARE_API_TOKEN。');
}
if (projectName !== 'slanwyf-imgbed') throw new Error('部署目标不是现有图床项目。');

const response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${account}/pages/projects/${projectName}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(30_000),
});
if (!response.ok) throw new Error(`Cloudflare 项目检查失败：HTTP ${response.status}。`);
const payload = await response.json();
if (!payload.success) throw new Error('Cloudflare 拒绝项目检查请求。');
const project = payload.result;
if (project.production_branch !== 'main') throw new Error('项目生产分支不是 main，停止发布。');
const production = project.deployment_configs?.production;
if (!production?.d1_databases?.img_d1?.id) throw new Error('现有项目缺少 img_d1 数据库绑定。');
for (const name of ['BASIC_USER', 'BASIC_PASS', 'AUTH_CODE', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY', 'S3_BUCKET_NAME', 'S3_ENDPOINT']) {
    if (!production.env_vars?.[name]) throw new Error(`现有项目缺少配置 ${name}。`);
}
if (production.compatibility_date !== '2026-11-14') {
    throw new Error('项目兼容日期与构建日期不同，请核对后一起更新。');
}
console.log('现有 Pages 项目、D1 绑定和配置检查通过。');

if (process.argv.includes('--verify-site')) {
    const origin = `https://${project.subdomain}`;
    const revision = process.env.GITHUB_SHA;
    const marker = await fetch(`${origin}/deployment.json?revision=${revision}`, {
        cache: 'no-store', signal: AbortSignal.timeout(30_000),
    });
    if (!marker.ok || (await marker.json()).revision !== revision) {
        throw new Error('线上部署提交与本次构建不一致。');
    }
    const home = await fetch(`${origin}/?revision=${revision}`, { signal: AbortSignal.timeout(30_000) });
    if (!home.ok || !(await home.text()).includes('<html')) throw new Error('线上首页检查失败。');
    const config = await fetch(`${origin}/api/userConfig?revision=${revision}`, { signal: AbortSignal.timeout(30_000) });
    if (!config.ok || (await config.json()).serverRuntime !== 'pages') throw new Error('线上 Pages 后端检查失败。');
    console.log(`线上前后端已验证：${origin}，提交 ${revision}`);
}
