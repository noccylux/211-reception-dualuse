"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const category = {IMMEDIATE_HUMAN:"立即人工", HUMAN_VERIFY:"人工核查", ROUTINE_HUMAN:"常规人工", AUTOMATION_ELIGIBLE:"可自动服务"};
  let token = "", state = null, busy = false;
  function element(tag, text, cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=String(text); if(cls)e.className=cls; return e; }
  function notice(text, error=false) { $("notice").textContent=text; $("notice").className=error?"notice-error":""; }
  async function request(path, payload) {
    const response=await fetch(`api/scoring/${path}`, {method:payload===undefined?"GET":"POST", headers:payload===undefined?{}:{"Content-Type":"application/json","X-CrisisFusion-Scoring":token}, body:payload===undefined?undefined:JSON.stringify(payload), cache:"no-store"});
    const data=await response.json(); if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail)); return data;
  }
  function fill(call) { $("call-id").value=call.call_id; $("revision").value=call.revision+1; $("language").value=call.language; $("transcript").value=call.text; $("location").value=call.location?.label||""; $("transcript").focus(); }
  function badge(assessment) { return element("span",assessment?`${assessment.score} · ${category[assessment.category]||assessment.category}`:"全部需求已解决",`badge ${assessment?.category||""}`); }
  function render() {
    const queue=$("queue"); queue.replaceChildren();
    if(!state.queue_calls.length)queue.append(element("p","暂无等待人工的通话。","muted"));
    state.queue_calls.forEach(call=>{const row=element("div",undefined,"queue-row");row.append(element("span",`#${call.queue_position} ${call.call_id}`),badge(call.priority_assessment),element("small",`${Math.floor(call.waiting_seconds)} 秒`));queue.append(row);});
    const calls=$("calls");calls.replaceChildren();
    if(!state.calls.length)calls.append(element("p","尚无通话。录入文字，或由宿主通过 API 发送累计转写。","muted"));
    state.calls.slice().reverse().forEach(call=>{
      const box=element("article",undefined,"call"), top=element("div",undefined,"call-top");
      top.append(element("h3",`${call.call_id} · 修订 ${call.revision}`),badge(call.priority_assessment));
      const edit=element("button","载入并修订","secondary");edit.onclick=()=>fill(call);top.append(edit);box.append(top,element("p",call.text,"quote"));
      const a=call.priority_assessment;
      if(a){
        if(a.safety_floor_applied)box.append(element("p","保留尚未解决需求的优先级下限；最新转写不能自动降级。","muted"));
        const ul=element("ul",undefined,"components");a.components.forEach(c=>{const li=element("li",`${c.label}: ${c.points>=0?"+":""}${c.points}`); if(c.evidence?.length){const q=c.evidence.map(e=>`r${e.revision??"人工"}「${e.quote}」`).join("；");li.append(element("p",q,"muted"));}ul.append(li);});box.append(ul);
        const details=element("details");details.append(element("summary","查看完整评分、约束及不确定性"),element("pre",JSON.stringify(a,null,2)));box.append(details);
      }
      state.needs.filter(n=>n.call_id===call.call_id&&n.unresolved).forEach(need=>{
        const panel=element("div",undefined,"need");panel.append(element("p",`${need.need_type} · ${category[need.triage_status]} · ${need.transfer_status}`));
        const form=element("form",undefined,"actions");const actor=element("input"),note=element("input"),choice=element("select");actor.required=true;actor.placeholder="核查人";note.required=true;note.placeholder="处理依据";
        [["resolve","人工解决此需求"],["HUMAN_VERIFY","升级至人工核查"],["IMMEDIATE_HUMAN","升级至立即人工"]].forEach(([value,text])=>{const opt=element("option",text);opt.value=value;choice.append(opt);});
        [["操作者",actor],["理由",note],["操作",choice]].forEach(([text,input])=>{const label=element("label",text);label.append(input);form.append(label);});
        const submit=element("button","记录处理");submit.type="submit";form.append(submit);
        form.onsubmit=async(e)=>{e.preventDefault();if(busy)return;const payload={action:choice.value==="resolve"?"resolve":"escalate",actor:actor.value.trim(),note:note.value.trim(),event_id:`manual-${crypto.randomUUID()}`};if(payload.action==="escalate")payload.target_category=choice.value;await mutate(()=>request(`needs/${encodeURIComponent(need.id)}/actions`,payload),"已保存人工操作。");};panel.append(form);box.append(panel);
      });calls.append(box);
    });
  }
  async function refresh() { state=await request("state");render(); }
  async function mutate(fn,message) {busy=true;document.querySelectorAll("button").forEach(b=>b.disabled=true);try{await fn();await refresh();notice(message);}catch(e){notice(e.message,true);}finally{busy=false;document.querySelectorAll("button").forEach(b=>b.disabled=false);}}
  $("call-form").onsubmit=async(e)=>{e.preventDefault();if(busy)return;const payload={call_id:$("call-id").value.trim(),revision:Number($("revision").value),text:$("transcript").value,language:$("language").value,location:$("location").value.trim()?{label:$("location").value.trim()}:{} };await mutate(()=>request("calls",payload),"通话已保存；评分与队列已更新。");};
  $("refresh").onclick=()=>mutate(()=>Promise.resolve(),"已刷新等待时间和评分。");
  (async()=>{try{const status=await request("status");token=status.csrf_token;$("policy").textContent=JSON.stringify(await request("policy"),null,2);await refresh();notice("本地评分已就绪 · 无需 API Key");}catch(e){notice(e.message,true);}})();
})();
