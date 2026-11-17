import {datasets, jobs, closure} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {ClosureStatus, PeriodStatus, RetestResult} from '../constants/enums.js';
import {esc, date, fmt, notify, toLocalInput, fromLocalInput} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

const canWrite = () => session.user.role !== 'viewer';
const isAdmin = () => session.user.role === 'admin';

const badge = (value, map, tone = '') => '<span class="closure-badge ' + esc(tone || value) + '">' + esc(map[value] || value) + '</span>';

export async function closurePage(id) {
 const [orders, allJobs, list, stats] = await Promise.all([
   closure.orders(), jobs.list(), datasets.list(), closure.stats()]);
 workspace.closureOrders = orders; workspace.jobs = allJobs; workspace.datasets = list;
 const approvedJobs = allJobs.filter(j => j.approved && j.status === 'completed');
 if (id) return closureDetail(Number(id), approvedJobs);
 return heading('06 / CLOSURE', '缺陷带销项与复测验收',
   '销项单从已批准试验的缺陷带建立，范围、参数与完工时间固定；复测按采集时间与覆盖范围登记，按原参数重算后与销项状态同时生效。')
   + '<section class="closure-stats">'
   + [['销项单', stats.orders], ['已销项', stats.closed], ['跟踪中', stats.open], ['复测凭据', stats.retests]]
       .map(([k, v]) => '<div><span>' + esc(k) + '</span><strong>' + esc(fmt(v)) + '</strong></div>').join('')
   + '</section>'
   + '<div class="closure-grid"><section class="panel">'
   + '<div class="section-title"><h2>建立销项单</h2><span>来源：已批准试验的缺陷带</span></div>'
   + createForm(approvedJobs)
   + '</section><section class="panel"><div class="section-title"><h2>销项单台账</h2><span>' + orders.length + ' 张</span></div>'
   + orderLedger(orders, allJobs)
   + '</section></div>';
}

function createForm(approvedJobs) {
 if (!approvedJobs.length) return '<p class="empty">尚无已批准的试验。请先在结果复核页批准一条分析结论。</p>';
 return '<form id="closure-create-form">'
   + '<label>来源已批准试验<select name="job_id" required>' + approvedJobs.map(j => '<option value="' + j.id + '">' + esc(j.name) + '</option>').join('') + '</select></label>'
   + '<label>缺陷带（孤立/稀疏点分组不可建单）<select name="band_key" required></select></label>'
   + '<label>两侧邻域宽度（米）<input type="number" name="neighborhood_m" value="100" min="1" max="5000" step="1" required></label>'
   + '<label>检修完工时间<input type="datetime-local" name="completed_at" required></label>'
   + '<label>销项单名称（可选）<input name="title" maxlength="160" placeholder="留空则按试验与缺陷带自动命名"></label>'
   + '<button type="submit" class="primary" ' + (canWrite() ? '' : 'disabled') + '>固定范围与参数，建立销项单 ↗</button>'
   + '<p class="hint">建单后范围、DBSCAN 参数与完工时间即冻结；复测只能引用，不能修改。观察员只读。</p></form>';
}

function orderLedger(orders, allJobs) {
 if (!orders.length) return '<p class="empty">还没有销项单。从左侧选择已批准试验的缺陷带建立第一张。</p>';
 const jobName = id => (allJobs.find(j => j.id === id) || {}).name || ('#' + id);
 return '<div class="order-list">' + orders.map(o => '<a class="order-card ' + esc(o.status) + '" href="#/closure/' + o.id + '">'
   + '<div class="order-card-head"><strong>' + esc(o.title) + '</strong>' + badge(o.status, ClosureStatus) + '</div>'
   + '<p>' + esc(jobName(o.job_id)) + ' · ' + esc(o.band_key) + '</p>'
   + '<small>原带 ' + esc(fmt(o.from_km)) + '~' + esc(fmt(o.to_km)) + ' km · 验收期第 ' + o.current_period + ' 期'
   + ' · 完工 ' + date(o.completed_at) + '</small>'
   + (o.status === 'closed' ? '<small class="ok-line">已于 ' + date(o.closed_at) + ' 销项</small>' : '<small class="warn-line">跟踪中，等待当期复测验收</small>')
   + '</a>').join('') + '</div>';
}

async function closureDetail(orderId, approvedJobs) {
 const detail = await closure.order(orderId);
 const o = detail.order;
 const job = workspace.jobs.find(j => j.id === o.job_id);
 return heading('06 / CLOSURE', '销项依据与验收期', o.title,
   '<a class="button" href="#/closure">返回销项台账 ↩</a>')
   + '<section class="panel order-spec"><div class="section-title"><h2>固定验收基线</h2><span>建单时冻结</span></div>'
   + '<div class="spec-grid">'
   + spec('来源试验', esc(job ? job.name : o.job_id))
   + spec('缺陷带', esc(o.band_key))
   + spec('原带范围（km）', esc(fmt(o.from_km)) + ' ~ ' + esc(fmt(o.to_km)))
   + spec('两侧邻域', esc(fmt(o.neighborhood_m)) + ' 米')
   + spec('复测必须覆盖（km）', esc(fmt(o.coverage_from_km)) + ' ~ ' + esc(fmt(o.coverage_to_km)))
   + spec('检修完工时间', date(o.completed_at))
   + spec('当前销项状态', badge(o.status, ClosureStatus))
   + spec('当前验收期', '第 ' + o.current_period + ' 期')
   + '</div><p class="eyebrow">固定 DBSCAN 参数</p><pre>' + esc(JSON.stringify(o.params, null, 2)) + '</pre></section>'
   + '<div class="closure-grid"><section class="panel">'
   + '<div class="section-title"><h2>登记复测</h2><span>采集时间与覆盖范围为凭据</span></div>'
   + retestForm(o)
   + '</section><section class="panel">'
   + (isAdmin() ? '<div class="section-title"><h2>返工管理</h2><span>开启新验收期</span></div>'
     + '<form id="rework-form"><label>返工原因<input name="reason" maxlength="300" placeholder="例如：补修后重新验收" required></label>'
     + '<button type="submit" class="primary">登记返工并开启第 ' + (o.current_period + 1) + ' 期 ↻</button>'
     + '<p class="hint">旧期全部复测证据保留但封存，不再用于新期结论；已销项会被撤销。仅业务负责人可登记返工。</p></form>'
     : '<p class="hint">返工登记仅业务负责人可操作；旧期证据始终保留可查。</p>')
   + '</section></div>'
   + '<section class="panel"><div class="section-title"><h2>验收期与复测依据</h2><span>' + detail.retests.length + ' 条复测凭据</span></div>'
   + periodsBlock(detail.periods, detail.retests)
   + '</section>';
}

function spec(label, value) {
 return '<div class="spec-item"><span>' + label + '</span><strong>' + value + '</strong></div>';
}

function retestForm(o) {
 if (o.status === 'closed') return '<p class="empty">该销项单已销项。如复检发现新问题，由业务负责人登记返工后开启新验收期。</p>';
 const now = toLocalInput(Date.now() / 1000);
 return '<form id="retest-form">'
   + '<label>复测数据批次<select name="dataset_id" required>' + workspace.datasets.map(d => '<option value="' + d.id + '">' + esc(d.name) + ' · ' + d.rows + ' 条</option>').join('') + '</select></label>'
   + '<label>现场采集时间<input type="datetime-local" name="collected_at" value="' + now + '" required></label>'
   + '<div class="parameter-grid"><label>覆盖起点（km）<input type="number" step="0.0001" name="coverage_from_km" required></label>'
   + '<label>覆盖终点（km）<input type="number" step="0.0001" name="coverage_to_km" required></label></div>'
   + '<label>现场备注（可选）<textarea name="note" rows="3" maxlength="2000" placeholder="零缺陷复测也请登记，覆盖凭据同样有效"></textarea></label>'
   + '<button type="submit" class="primary" ' + (canWrite() ? '' : 'disabled') + '登记复测并按固定参数重算 ↗</button>'
   + '<p class="hint">采集时间须晚于' + (o.current_period > 1 ? '本验收期开启（返工）时间与' : '') + '完工 ' + date(o.completed_at)
   + '；覆盖须含原带及两侧邻域 '
   + esc(fmt(o.coverage_from_km)) + '~' + esc(fmt(o.coverage_to_km)) + ' km。同期同批次重复登记只返回原结论，不新增记录。</p></form>';
}

function periodsBlock(periods, retests) {
 return periods.map(p => {
   const items = retests.filter(r => r.period_id === p.id);
   const tone = p.status === 'accepted' ? 'accepted' : (p.status === 'superseded' ? 'superseded' : 'active');
   return '<article class="period-block ' + tone + '"><div class="period-head"><strong>第 ' + p.period_no + ' 验收期</strong>'
     + badge(p.status, PeriodStatus, tone) + '<small>' + esc(p.reason || '初始验收期') + ' · 开启 ' + date(p.opened_at)
     + (p.closed_at ? ' · 封存 ' + date(p.closed_at) : '') + '</small></div>'
     + (items.length ? items.map(retestCard).join('') : '<p class="empty">本期尚无复测登记。</p>')
     + '</article>';
 }).join('');
}

function retestCard(r) {
 const f = r.findings || {};
 const cred = f.coverage_credential || {};
 const timeCred = f.time_credential || {};
 return '<div class="retest-card ' + esc(r.result) + '"><div class="retest-head"><strong>复测 #' + r.id + ' · 第 ' + r.period_no + ' 期</strong>'
   + badge(r.result, RetestResult, r.result) + '</div>'
   + '<div class="credential-grid">'
   + credLine('采集时间', date(r.collected_at), r.time_ok,
       '晚于' + (timeCred.threshold_label || '完工') + ' ' + date(timeCred.required_after ?? timeCred.completed_at))
   + credLine('覆盖范围', esc(fmt(r.coverage_from_km)) + ' ~ ' + esc(fmt(r.coverage_to_km)) + ' km', r.coverage_ok,
       '要求 ' + esc(fmt(cred.required_from_km)) + ' ~ ' + esc(fmt(cred.required_to_km)) + ' km')
   + credLine('原带内点数', String(f.in_band_records ?? '—'), true, f.zero_defect ? '零缺陷，覆盖凭据仍有效' : '')
   + credLine('重算核心点', String(r.core_points_in_band), r.core_points_in_band === 0, '固定参数重算')
   + credLine('高等级孤立点', String(r.high_isolated_in_band), r.high_isolated_in_band === 0, '等级≥4 的孤立/噪声点')
   + '</div>'
   + (r.reject_reasons && r.reject_reasons.length ? '<ul class="reject-list">' + r.reject_reasons.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>'
     : '<p class="ok-line">时间、覆盖与重算口径全部满足，结论与销项状态同时生效。</p>')
   + (f.core_point_ids && f.core_point_ids.length ? '<p class="mini">核心点编号：' + esc(f.core_point_ids.join('、')) + '</p>' : '')
   + (f.high_isolated_ids && f.high_isolated_ids.length ? '<p class="mini">高等级孤立点编号：' + esc(f.high_isolated_ids.join('、')) + '</p>' : '')
   + '<p class="mini">数据批次 #' + r.dataset_id + ' · SHA256 ' + esc(r.dataset_checksum.slice(0, 24)) + '… · 登记于 ' + date(r.registered_at) + (r.note ? ' · ' + esc(r.note) : '') + '</p>'
   + '</div>';
}

function credLine(label, value, ok, hint) {
 return '<div class="cred-item"><span>' + esc(label) + '</span><strong>' + value + '</strong>'
   + '<small class="' + (ok ? 'ok-text' : 'bad-text') + '">' + (ok ? '✓ ' : '✗ ') + esc(hint || (ok ? '满足' : '不满足')) + '</small></div>';
}

export function bindClosure(refresh) {
 const jobSelect = document.querySelector('[name=job_id]');
 const bandSelect = document.querySelector('[name=band_key]');
 const completedInput = document.querySelector('[name=completed_at]');
 if (completedInput && !completedInput.value) completedInput.value = toLocalInput(Date.now() / 1000);
 async function loadBands() {
   if (!jobSelect || !bandSelect) return;
   try {
     const rows = await closure.bands(Number(jobSelect.value));
     bandSelect.innerHTML = rows.map(b => '<option value="' + esc(b.band) + '">' + esc(b.band)
       + '（' + esc(fmt(b.from_km)) + '~' + esc(fmt(b.to_km)) + ' km，' + b.count + ' 点）</option>').join('');
   } catch (e) { notify(e.message, true); }
 }
 if (jobSelect) { jobSelect.addEventListener('change', loadBands); loadBands(); }
 const createForm = document.querySelector('#closure-create-form');
 if (createForm) submit(createForm, async f => {
   const completedAt = fromLocalInput(f.get('completed_at'));
   if (!completedAt) throw new Error('请选择有效的完工时间');
   const title = (f.get('title') || '').trim();
   const created = await closure.createOrder({
     job_id: Number(f.get('job_id')), band_key: f.get('band_key'),
     neighborhood_m: Number(f.get('neighborhood_m')), completed_at: completedAt,
     ...(title ? {title} : {}),
   });
   notify('销项单已建立，范围与参数已固定');
   location.hash = '#/closure/' + created.id;
 });
 const retestForm = document.querySelector('#retest-form');
 if (retestForm) submit(retestForm, async f => {
   const collectedAt = fromLocalInput(f.get('collected_at'));
   if (!collectedAt) throw new Error('请选择有效的采集时间');
   const id = Number(location.hash.split('/')[2]);
   const body = await closure.registerRetest({
     order_id: id, dataset_id: Number(f.get('dataset_id')), collected_at: collectedAt,
     coverage_from_km: Number(f.get('coverage_from_km')),
     coverage_to_km: Number(f.get('coverage_to_km')),
     note: (f.get('note') || '').trim(),
   });
   notify(body.duplicated ? '该批次本期已登记，返回既有结论（未新增记录）'
     : (body.retest.result === 'passed' ? '复测通过，销项状态已同步生效' : '复测不予销项，依据已登记'));
   await refresh();
 });
 const reworkForm = document.querySelector('#rework-form');
 if (reworkForm) submit(reworkForm, async f => {
   const id = Number(location.hash.split('/')[2]);
   await closure.rework(id, (f.get('reason') || '').trim());
   notify('返工已登记，新验收期开启；旧期证据已封存保留');
   await refresh();
 });
}
