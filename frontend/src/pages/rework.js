import{heading}from'../components/labels.js';import{esc,kg,formData}from'../utils/format.js';import{api}from'../utils/api.js';import{PELLET_STATES}from'../constants.js';
const isQuarantine=x=>x.state==='quarantine';
const reworkedOf=(s,id)=>s.reworks.filter(o=>o.source_check_id===id).reduce((a,o)=>a+Number(o.kg),0);
export function render(s,u){
  const p=s.pellets.find(x=>x.id===s.reworkSelected)||s.pellets.find(isQuarantine)||s.pellets[0];
  const quar=s.pellets.filter(isQuarantine);
  const totalRework=s.reworks.reduce((a,o)=>a+Number(o.kg),0);
  return heading('07','隔离料不再只靠手账返混。','按重量把隔离粒料拆成可追溯返工料包；源粒料扣除返工量后才复检发证，已签证拒绝返工，原检验与投料快照冻结。',s.reworks.length,'返工拆包单')
  +`<div class="quality-flow"><aside><h2>隔离粒料（可返工）</h2><div class="lot-list">${(quar.length?quar:s.pellets).map(x=>{const rw=reworkedOf(s,x.id);return `<button class="lot-pick ${x.id===p?.id?'selected':''}" data-reworkpick="${x.id}"><b>${esc(x.blend_code)}</b><span>${PELLET_STATES[x.state]} · 检出${kg(x.actual_kg)}kg${rw?` · 已返工${kg(rw)}kg`:''}</span></button>`}).join('')||'<p class="tiny">暂无隔离粒料。</p>'}</div><h2 style="margin-top:18px">返工拆包记录</h2><div class="lot-list">${s.reworks.map(o=>`<button class="lot-pick" data-reworkpick="${o.source_check_id}"><b>${esc(o.code)} · G${o.generation}</b><span>${esc(o.new_bale_code)} · ${kg(o.kg)}kg</span></button>`).join('')||'<p class="tiny">尚未办理返工拆包。</p>'}</div></aside><section>${p?renderDetail(s,p,u,totalRework):'<div class="empty">先在粒料检验页对已投料配方取样，PVC越限的隔离料会出现在这里。</div>'}</section></div>`;
}
function renderDetail(s,p,u,totalRework){
  const rw=reworkedOf(s,p.id);const certifiable=Number(p.actual_kg)-rw;const waiting=Math.max(certifiable,0);
  const events=s.reworks.filter(o=>o.source_check_id===p.id);
  const canSplit=p.state==='quarantine'&&u.role!=='viewer'&&certifiable>0;
  return `<div class="scalehead"><h2>${esc(p.blend_code)} · 粒料处置</h2><span class="tag ${p.state}">${PELLET_STATES[p.state]}</span></div>
  <div class="quality-metrics">
    <div><small>粒料检出重量</small><strong>${kg(p.actual_kg)} kg</strong></div>
    <div><small>待返工可拆重量</small><strong>${kg(waiting)} kg</strong></div>
    <div><small>累计已返工重量</small><strong class="quarantine">${kg(rw)} kg</strong></div>
    <div><small>可发证（可售）重量</small><strong class="passed">${kg(certifiable)} kg</strong></div>
  </div>
  <p class="note trace-note">可发证 = 检出 − 已返工。已返工重量不会再算成可售产出；包装与发证均以此为上限。全场累计已返工 <b>${kg(totalRework)} kg</b>。</p>
  ${p.state==='certified'?'<div class="certificate"><p class="tiny">该料已签发合格证，签证与快照冻结，<b>拒绝任何返工拆包</b>。</p></div>':''}
  ${p.state==='passed'?'<div class="certificate"><p class="tiny">该料已复检合格，请走粒料检验页发证；合格料不再返工。</p></div>':''}
  ${canSplit?`<form id="rework-create" data-id="${p.id}"><h3>按重量拆出返工料包</h3><div class="grid2"><label>拆出重量 kg（≤${kg(certifiable)}）<input name="kg" type="number" min="0.001" step="0.001" max="${certifiable}" required></label><label>幂等令牌（可选，重试同单）<input name="request_token" placeholder="留空则按同重量同依据去重" maxlength="80"></label></div><label>返工处置依据<textarea name="reason" minlength="8" required placeholder="筛除、清线或重造依据，至少8字"></textarea></label><button class="orange">拆出返工料包（同事务扣源料+建新包）</button></form>`:''}
  ${p.state==='quarantine'&&certifiable<=0?'<p class="tiny">该料已全部返工拆出，没有可发证重量；新料包重新分群检验后再投料。</p>':''}
  <div class="inspection-history"><h3>返工拆包与代际追溯</h3>${events.map(o=>`<p><b>${esc(o.code)} · 第${o.generation}代 · ${kg(o.kg)}kg</b>　新包 <b>${esc(o.new_bale_code)}</b>（待重新分群）<br><small>${esc(o.reason)} · ${esc(o.created_by)} · 血统深度${o.lineage_depth}代</small></p>`).join('')||'<p class="tiny">本份料还没有返工记录。</p>'}</div>
  <details open><summary>原检验与投料快照（保留不动）</summary><p class="tiny">PVC门限 ${p.input_snapshot.max_pvc}ppm · 投料 ${kg(p.input_snapshot.total_kg)}kg · 检验${p.inspections.length}次；返工不覆盖首次异常。</p>${p.input_snapshot.portions.map(x=>`<p class="tiny">${esc(x.bale_code)} / ${kg(x.kg)}kg / PVC ${x.pvc_snapshot}ppm / 群${x.cluster_snapshot+1}</p>`).join('')}</details>
  ${p.state==='quarantine'?`<p class="note">拆出后到「可混群落」对 RW 返工包重新分群，再按同群规则立单投料；再次隔离仍可返工，各代来源与累计重量在上方追溯。复检发证请前往 <a href="#pellets">粒料检验放行</a>。</p>`:''}`;
}
export function bind(refresh,render,s){
  document.querySelectorAll('[data-reworkpick]').forEach(x=>x.onclick=()=>{s.reworkSelected=+x.dataset.reworkpick;render()});
  const f=document.querySelector('#rework-create');
  if(f)f.onsubmit=e=>{e.preventDefault();const d=formData(f);d.kg=Number(d.kg);d.check_id=Number(f.dataset.id);if(!d.request_token)delete d.request_token;refresh(async()=>{const o=await api('/rework-orders','POST',d);s.reworkSelected=o.source_check_id},'返工料包已拆出，源粒料同步扣除，原快照保留')};
}
