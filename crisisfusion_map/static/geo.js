/* Optional map: no automatic geolocation, network feeds, or priority changes. */
(() => {
  'use strict';
  const section = document.createElement('section'); section.id = 'geo'; section.className = 'active';
  section.innerHTML = `
    <div class="panel geo-intro"><div class="eyebrow">OPTIONAL LOCATION & EVENT PLUGIN / LOS ANGELES COUNTY</div><h2>通话地址判断与区域风险</h2><p>先判断通话是否提供可用地址，再核实坐标与当前事件区域的关系。<strong>标记形状表示地址核实状态，标记颜色表示有来源的区域风险背景</strong>；通话优先级单独显示，不由地图颜色决定。</p><p>设备定位与报告事件地点分开记录。当前官方来源为 NWS 天气预警和 USGS 县内震中（近 7 天、M ≥ 2.5）；不完整覆盖火场、疏散区或枪击警戒区。灰色表示未知，不代表安全。</p><div id="geo-message" class="geo-message" role="status" aria-live="polite"></div></div>
    <details class="panel geo-standards"><summary>查看判断标准：地址是否可定位、准确性与紧急区等级</summary><div class="geo-standards-body"><p>这是原型中的可解释判断规则，不是经过验证的派遣或安全等级。每个结论保留来源、时间、匹配关系和缺失信息；本系统没有测得地址识别准确率，不展示虚构的置信度百分比。</p><div class="geo-table-scroll"><table><caption>地址判断与地图形状</caption><thead><tr><th>状态</th><th>判定含义</th><th>地图表示</th></tr></thead><tbody><tr><td>无地址 / 仅区域</td><td>没有具体地点，或只有城市、街区等宽泛描述</td><td>保留在通话列表；没有坐标就不画点</td></tr><tr><td>地址候选</td><td>从通话原文发现具体地点表述，尚未获得或核查坐标</td><td>没有坐标就不画点；保留原话与修订号</td></tr><tr><td>已定位 / 未核实</td><td>有坐标候选，但尚未由人工确认与本次报告一致</td><td>空心菱形 ◇</td></tr><tr><td>人工已确认</td><td>核查人确认地址、坐标和依据；不等于独立证明真实位置</td><td>实心圆 ●</td></tr><tr><td>地点存在冲突</td><td>地点信息不一致，需要核对最新有效地址</td><td>叉形 ×；不擅自选择冲突地址</td></tr></tbody></table></div><div class="geo-table-scroll"><table><caption>区域背景等级（仅用于本原型）</caption><thead><tr><th>颜色 / 等级</th><th>判断依据与限制</th></tr></thead><tbody><tr><td><span class="geo-risk-swatch unknown"></span>未知 UNKNOWN</td><td>地址不完整、没有适用区域、来源过时或缺少覆盖；无重叠也不能判为安全</td></tr><tr><td><span class="geo-risk-swatch info"></span>信息 INFO</td><td>存在相关事件信息；震中点本身不能说明该地址受损或处于危险区</td></tr><tr><td><span class="geo-risk-swatch watch"></span>关注 WATCH</td><td>有当前来源支持的关注级区域关系，需查看原始预警与具体匹配依据</td></tr><tr><td><span class="geo-risk-swatch high"></span>高 HIGH</td><td>匹配到当前较高等级区域背景；精度范围与区域边缘相交需另行核实</td></tr><tr><td><span class="geo-risk-swatch critical"></span>紧急 CRITICAL</td><td>匹配到当前最高等级区域背景；不表示系统已经确认来电者现场危险</td></tr></tbody></table></div><p><strong>边界与数据限制：</strong>Red Flag Warning 是火险气象条件，不是已发生火灾的火场。地震震中没有自动扩出的“受灾半径”。枪击等事件缺少已核实警戒边界时，不能生成已确认危险区。查看每张卡片的来源、有效期与空间匹配依据。</p><p id="geo-policy-version" class="geo-note"></p></div></details>
    <div class="geo-layout"><div class="panel geo-map-panel">
      <div class="geo-toolbar"><button id="geo-fit" class="ghost">返回 LA County</button><label><input id="geo-basemap" type="checkbox"> 加载在线街道底图</label><button id="geo-reload" class="ghost">更新本地记录</button></div>
      <div class="geo-legend"><label><input id="geo-layer-calls" type="checkbox" checked><span class="geo-legend-diamond"></span>通话地址判断</label><label><input id="geo-layer-device" type="checkbox" checked><span class="geo-dot" style="background:#2878ba"></span>通话设备（独立图层）</label><label><input id="geo-layer-reports" type="checkbox" checked><span class="geo-dot" style="background:#c47b26"></span>人工报告</label><label><input id="geo-layer-official" type="checkbox" checked><span class="geo-dot" style="background:#8654b1"></span>官方发布</label></div>
      <div class="geo-risk-legend" aria-label="通话地址标记图例"><span>地址形状：● 人工确认 · ◇ 未核实 · × 冲突</span><span><i class="geo-risk-swatch unknown"></i>未知</span><span><i class="geo-risk-swatch info"></i>信息</span><span><i class="geo-risk-swatch watch"></i>关注</span><span><i class="geo-risk-swatch high"></i>高</span><span><i class="geo-risk-swatch critical"></i>紧急</span><strong>颜色不等于通话优先级</strong></div>
      <div id="geo-map" class="geo-map" aria-label="Los Angeles County location and event map"></div>
      <p id="geo-map-note" class="geo-note">县界已随应用保存在本机。勾选街道底图后，浏览器会向 OpenStreetMap 请求当前视野的图块（暴露 IP 和地图视野）；不会发送通话原文或标记数据。</p>
      <div class="panel-title"><h2>逐通话地址与区域判断</h2><span id="geo-assessment-count" class="mini"></span></div><div id="geo-assessments" class="geo-card-grid"></div>
      <div class="panel-title"><h2>来源记录 / 可核查详情</h2><span id="geo-count" class="mini"></span></div><div id="geo-records" class="geo-card-grid"></div>
    </div><aside class="panel geo-sidebar">
      <h2>可插拔模块</h2><p class="geo-note" style="padding:9px 0">开启后可保存本次通话的授权位置；关闭会隐藏图层并停止数据请求，已有记录保留。可单独删除设备位置。</p><button id="geo-toggle" class="primary">启用地图插件</button>
      <h3>官方事件数据源</h3><div id="geo-providers"></div><button id="geo-refresh" class="ghost">获取 / 刷新官方事件</button><p class="geo-note" style="padding:10px 0">手动刷新，最短间隔 60 秒。失败时保留旧记录并标为过时；不承诺完整覆盖或实时告警。</p>
      <details id="geo-address-details"><summary>核查本次通话的报告地址</summary><form id="geo-address-form"><label for="geo-address-call">关联 Call ID</label><select id="geo-address-call" required></select><label for="geo-address-label">报告地点 / 待查询地址</label><input id="geo-address-label" required maxlength="300" placeholder="门牌号、街道、城市、CA；核对来电原话"><p class="geo-note geo-form-note">这里核查的是来电者报告的地点。设备 GPS 不会自动填成事件地址。可直接填写已核实坐标，或自愿使用 Census 地址查询。</p><label class="geo-check"><input id="geo-geocode-consent" type="checkbox"><span>同意仅将上方填写的地址发送至美国 Census 地理编码服务；不会发送通话原文。查询结果可能是沿街道插值得到的坐标，不代表实测位置或准确率。</span></label><button id="geo-geocode" type="button" class="ghost">查询地址候选坐标</button><div id="geo-geocode-results" class="geo-geocode-results" role="status" aria-live="polite"></div><div class="form-row"><div><label for="geo-address-lat">纬度 Latitude</label><input id="geo-address-lat" type="number" step="any" min="-90" max="90" required></div><div><label for="geo-address-lon">经度 Longitude</label><input id="geo-address-lon" type="number" step="any" min="-180" max="180" required></div></div><button id="geo-address-pick" type="button" class="ghost">在地图上选报告地址</button><label for="geo-address-accuracy">已知位置误差范围（米，可选）</label><input id="geo-address-accuracy" type="number" min="1" max="100000" step="any" placeholder="不确定则留空；不是识别准确率"><label for="geo-address-reviewer">核查人</label><input id="geo-address-reviewer" required maxlength="100" placeholder="姓名或工作标识"><label for="geo-address-note">核查依据 / 对冲突的说明</label><textarea id="geo-address-note" required minlength="10" maxlength="2000" placeholder="例如：与来电者复述地址确认，依据哪条原话及如何核对坐标。至少 10 字符。"></textarea><label class="geo-check"><input id="geo-address-confirmed" type="checkbox" required>我已核对地址与坐标，并确认它们对应本次通话报告的地点</label><button id="geo-address-save" type="submit" class="primary">保存人工地址确认</button><button id="geo-address-clear" type="button" class="ghost">清除本通话的地址确认</button></form></details>
      <details><summary>标注来电报告的事件地点</summary><form id="geo-report-form"><label for="geo-call">关联 Call ID</label><select id="geo-call" required></select><label for="geo-label">事件 / 地点名称</label><input id="geo-label" required maxlength="200" placeholder="例：来电者报告的道路积水"><div class="form-row"><div><label for="geo-lat">纬度 Latitude</label><input id="geo-lat" type="number" step="any" min="-90" max="90" required></div><div><label for="geo-lon">经度 Longitude</label><input id="geo-lon" type="number" step="any" min="-180" max="180" required></div></div><button id="geo-pick" type="button" class="ghost">在地图上选事件地点</button><label for="geo-note">证据 / 核查记录（至少 10 字符）</label><textarea id="geo-note" minlength="10" maxlength="2000" required placeholder="记录来电原话、核查方式及依据；不要把设备定位当作事件确认。"></textarea><label for="geo-source">证据链接（可选 HTTPS）</label><input id="geo-source" type="url" placeholder="https://..."><label class="geo-check"><input id="geo-reviewed" type="checkbox">我已人工核查并在上述记录说明依据（仍不等于官方确认）</label><button id="geo-report-save" class="primary" type="submit">保存人工报告</button></form></details>
      <p class="geo-note" style="padding:15px 0 0">真实县界：LA County GIS（经简化）。地图仅用于原型信息汇总，不是导航、完整应急告警或派遣系统。</p>
    </aside></div>`;
  document.getElementById('plugin-root').append(section);
  section.querySelectorAll('.geo-standards table').forEach(table=>{const headings=[...table.querySelectorAll('thead th')].map(cell=>cell.textContent);table.querySelectorAll('tbody tr').forEach(row=>[...row.children].forEach((cell,index)=>{cell.dataset.label=headings[index];}));});
  document.getElementById('geo-policy-version').insertAdjacentHTML('beforebegin','<p><strong>NWS 官方预警的具体判定：</strong>只有 Actual 状态的 Alert / Update、有有效时间和区域多边形、且来源在最近 5 分钟内成功获取时，才参与当前背景等级。CAP Severity 的 Minor → INFO、Moderate → WATCH、Severe → HIGH、Extreme → CRITICAL；Urgency 必须为 Immediate / Expected。Certainty 为 Possible / Unlikely 时最高显示 WATCH；Observed / Likely 保留映射等级。取消、过期、未来生效、关键字段缺失或缓存过时均不能形成当前等级。</p><p><strong>空间匹配与合并：</strong>点落入多边形、误差圆整体落入区域、以及边界附近可能重叠会分别说明；边界采用 25 米的原型保护距离。有效匹配取最高背景等级，但未确认地址仅表示条件性关联；冲突或已失效的地址确认会使当前汇总回到未知。操作员填写的有效人工圆形范围可提供单独标明的背景依据，始终不是官方区域。合成演示范围不参与当前区域等级。</p>');
  document.getElementById('geo-address-call').insertAdjacentHTML('afterend','<p id="geo-address-revision" class="geo-note geo-form-note" role="status"></p><button id="geo-address-reload" type="button" class="ghost">重新载入当前地址与修订</button>');
  document.getElementById('geo-pick').insertAdjacentHTML('afterend',`<label for="geo-hazard">事件类型</label><select id="geo-hazard"><option value="other">其他 / 未分类</option><option value="fire">火灾</option><option value="earthquake">地震</option><option value="shooting">枪击</option></select><details class="geo-manual-zone"><summary>人工核查范围（可选，非官方警戒区）</summary><p class="geo-note geo-form-note">只有掌握核查依据时才填写半径。该圆形是操作员记录的范围，不能当作官方警戒线或实际影响范围；留空仅显示报告点。</p><label for="geo-zone-radius">核查范围半径（米，10–10000；可留空）</label><input id="geo-zone-radius" type="number" min="10" max="10000" step="any" placeholder="留空不生成区域"><label for="geo-zone-level">记录的区域背景等级</label><select id="geo-zone-level"><option value="INFO">信息 INFO</option><option value="WATCH" selected>关注 WATCH</option><option value="HIGH">高 HIGH</option><option value="CRITICAL">紧急 CRITICAL</option></select><label for="geo-zone-minutes">有效时间（分钟，1–1440）</label><input id="geo-zone-minutes" type="number" min="1" max="1440" value="60"><p class="geo-note geo-form-note">保存范围还需要 HTTPS 证据链接、核查说明，并勾选人工核查。过期后不作为当前区域依据。</p></details>`);
  const shortcuts=document.createElement('div');shortcuts.className='voice-button-row';shortcuts.innerHTML='<button id="geo-quick-toggle" class="primary">启用地图插件</button><button id="geo-quick-refresh" class="ghost">刷新官方事件</button>';section.querySelector('.geo-intro').append(shortcuts);
  const gps = document.createElement('div'); gps.className = 'geo-location-controls';
  gps.innerHTML = `<strong>本次通话的位置（可选）</strong><p>开始语音后，可授权获取<strong>当前通话网页所在设备</strong>的位置和精度，并保存在本机。它可能是 Wi-Fi / 网络估计；不能通过电话号码定位远端来电者。拒绝定位不影响通话。</p><label><input id="geo-consent" type="checkbox"><span>我同意将本次设备位置与当前通话关联；不会自动持续跟踪。</span></label><div class="voice-button-row"><button id="geo-locate" type="button" class="ghost">授权并定位当前通话</button><button id="geo-show-map" type="button" class="ghost">打开 LA County 地图</button></div><p id="geo-gps-message" role="status">先启用地图插件，再开始网页语音；每次通话单独授权。</p>`;
  gps.querySelector('p').textContent='先由宿主明确标记活动通话，再选择下面的通话并授权定位本网页所在设备。不能通过电话号码定位远端来电者；设备位置与报告事件地址独立保存。';
  gps.querySelector('strong').insertAdjacentHTML('afterend','<label for="geo-active-call">关联活动通话</label><select id="geo-active-call"></select>');
  gps.querySelector('#geo-gps-message').textContent='先启用插件，选择宿主标记为活动的通话，再单独授权设备定位。';
  section.querySelector('.geo-sidebar').prepend(gps);
  const el = id => document.getElementById('geo-' + id);
  let data = null, map = null, tiles = null, boundary = null, layers = null, busy = false, picking = null, gpsBusy = false, gpsGeneration = 0, voiceCallId = null, lastRender = '', lastAddressCall = '', addressReviewRevision = null;
  const colours = {device:'#2878ba',report:'#c47b26',official:'#8654b1'};
  const riskColours = {UNKNOWN:'#64748b',INFO:'#2563eb',WATCH:'#eab308',HIGH:'#f97316',CRITICAL:'#dc2626'};
  const addressNames = {NO_ADDRESS:'无可用地址',AREA_ONLY:'只有区域描述',ADDRESS_CANDIDATE:'发现地址候选',LOCATED_UNCONFIRMED:'已定位 · 尚未核实',HUMAN_CONFIRMED:'人工已确认',CONFLICT:'地址信息存在冲突'};
  const riskNames = {UNKNOWN:'未知',INFO:'信息',WATCH:'关注',HIGH:'高',CRITICAL:'紧急'};
  const hazardNames = {fire:'火灾',fire_weather:'火险气象条件',earthquake:'地震',shooting:'枪击',other:'其他事件',FIRE_WEATHER:'火险气象条件',EARTHQUAKE:'地震',SHOOTING:'枪击',FIRE:'火灾'};
  const detailNames={
    official_nws:'NWS 官方来源',local_operator:'本地操作员记录 / 非官方',operator_confirmed:'操作员确认坐标',census_geocoder_interpolated:'Census 地址插值坐标',
    civic_address:'门牌与街道',intersection:'交叉路口',landmark:'地标',named_place:'命名地点',area:'区域',caller:'来电原话',prior_confirmation:'较早的人工确认',transcript:'通话原文',reported_label:'报告地点字段',uncertain:'地址表述不确定',approximate:'大致位置或附近',reported:'转述信息，未经独立核实',negated:'否定的地点表述',historical:'历史地点表述',WITHIN_REPORTED_ACCURACY:'已知误差圆在区域内（局部几何近似）',
    address_reference:'地址表述',street_address_or_cross_streets:'街道地址或交叉路口',building_number_or_exact_side:'门牌或路口具体方位',incident_coordinates:'报告地点坐标',human_confirmation:'人工确认',city_or_postal_code:'城市或邮政编码',conflict_resolution:'地址冲突处理',
    address_from_prior_revision:'地址来自较早修订',multiple_specific_addresses:'存在多个具体地址',address_changed_between_revisions:'不同修订中的地址发生变化',previous_address_retracted:'先前地址已被撤回',device_coordinates_excluded:'已排除设备坐标，不将其当作事件地点',stale_confirmation:'人工确认对应的通话修订已过时',current_address_differs_from_stale_point:'当前地址与较早确认点不一致',incomplete_confirmation:'人工确认信息不完整',conflict_resolved_by_operator:'操作员已记录地址冲突处理',asr_transcription_unverified:'语音转写尚未核实',
    OFFICIAL_SHOOTING_COVERAGE_UNAVAILABLE:'没有接入官方枪击事件或警戒区完整数据',NO_MATCH_DOES_NOT_MEAN_SAFE:'没有匹配事件不代表地点安全',EVENT_ADDRESS_COORDINATES_MISSING_OR_INVALID:'报告地址缺少有效坐标',ADDRESS_COORDINATE_PRECISION_UNKNOWN:'坐标误差范围未知',ADDRESS_NOT_CONFIRMED_ASSOCIATION_IS_CONDITIONAL:'报告地址未人工确认，区域关联仅在该候选地址成立时适用',ADDRESS_CHANGED_OR_CONFLICT_RECONFIRM_BEFORE_CURRENT_CLASSIFICATION:'地址发生变化或冲突，需要重新核实后才能作为当前判断',NWS_COVERAGE_UNAVAILABLE_OR_STALE:'NWS 来源不可用或已过时',EVENT_LIMIT_REACHED_COVERAGE_INCOMPLETE:'事件处理上限已达到，覆盖可能不完整',EARTHQUAKE_LOCAL_INTENSITY_NOT_AVAILABLE_FROM_EPICENTRES:'地震震中无法提供本地址的震动强度或受损范围',NWS_ALERT_AREA_UNAVAILABLE:'预警区域尚未加载或无有效多边形',NWS_SOURCE_LINK_UNAVAILABLE:'缺少可核对的 NWS 来源链接',NWS_STATUS_NOT_CURRENT_OR_UNVERIFIED:'NWS 状态不属于已确认的当前正式预警',NWS_VALIDITY_TIME_UNKNOWN:'NWS 有效时间未知',NWS_CAP_FIELDS_UNKNOWN_OR_NOT_CURRENT:'NWS 严重度、紧迫性或确定性不足以建立当前等级',GEOMETRY_WORK_LIMIT_REACHED_COVERAGE_INCOMPLETE:'几何处理上限已达到，空间覆盖可能不完整',REPORT_LIMIT_REACHED_COVERAGE_INCOMPLETE:'人工报告处理上限已达到',SYNTHETIC_LOCAL_AREAS_EXCLUDED_FROM_CURRENT_LEVELS:'合成演示范围不参与当前区域等级',LOCAL_AREA_GEOMETRY_INVALID:'人工区域几何数据无效',LOCAL_AREA_UNVERIFIED_OPERATOR_ASSUMPTION:'人工圆形范围是操作员提供的待验证假设，不是官方警戒区',
    POINT_INSIDE:'坐标点位于区域内，坐标误差范围未知',ACCURACY_CIRCLE_INSIDE:'已知误差圆位于区域内',POSSIBLE_BOUNDARY_OVERLAP:'在区域边界附近，可能重叠但不能确认位于区域内',AREA_UNAVAILABLE:'尚无有效区域几何',CANCELLED:'预警已取消',STATUS_UNVERIFIED:'来源状态待核实',FUTURE:'尚未生效',EXPIRED:'已到期或已结束',MANUAL_AREA_POTENTIAL:'可能关联人工核查范围 / 非官方',MANUAL_BOUNDARY_POSSIBLE:'可能与人工范围边界重叠 / 非官方',MANUAL_POINT_INSIDE:'坐标点在人工范围内，误差未知 / 非官方',MANUAL_EXPIRED_OR_UNDATED:'人工范围已过时或有效期不明',UNLOCATED:'地址尚未定位',NO_CURRENT_SUPPORTED_MATCH:'当前没有得到有效来源支持的区域匹配',ADDRESS_REQUIRES_RECONFIRMATION:'地址需要重新确认'
  };
  function describe(value){if(typeof value!=='string')return String(value??'');return detailNames[value]||(value.startsWith('CANDIDATE_')?'候选地址的条件性关联：'+describe(value.slice(10)):value);}
  const date = value => value ? new Date(value).toLocaleString('zh-CN', {timeZone:'America/Los_Angeles', hour12:false}) + ' PT' : '尚未获取';
  function say(message, error=false) {el('message').textContent=message;el('message').classList.toggle('error',error);}
  async function request(path='', body, method) {
    const controller = new AbortController(), timer=setTimeout(()=>controller.abort(),30000);
    try {
      const r=await fetch(new URL('api/geo/'+path,document.baseURI),{method:method||(body===undefined?'GET':'POST'),credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json',...(body!==undefined||method?{'X-CrisisFusion-Geo':data?.csrf_token||''}:{})},body:body===undefined?undefined:JSON.stringify(body)});
      const value=await r.json();if(!r.ok)throw new Error(typeof value.detail==='string'?value.detail:`地图请求失败 (${r.status})`);return value;
    } catch(e) {if(e.name==='AbortError')throw new Error('地图请求超时；保留本地记录，请稍后刷新。');throw e;} finally{clearTimeout(timer);}
  }
  function currentCall(){const selected=el('active-call').value;return data?.calls.some(call=>call.call_id===selected&&call.active)?selected:null;}
  function gpsControls(){
    const id=currentCall();if(id!==voiceCallId){voiceCallId=id;gpsGeneration++;el('consent').checked=false;el('gps-message').textContent=id?'当前通话 '+id+'：如需位置，请勾选授权后点击定位。':'当前没有选中的活动通话。由宿主标记通话活动后，再选择并授权设备定位。';}
    el('locate').disabled=gpsBusy||!data?.enabled||!id||!el('consent').checked;
  }
  function controls(){
    el('toggle').textContent=data?.enabled?'停用地图插件':'启用地图插件';el('toggle').disabled=busy;
    el('quick-toggle').textContent=el('toggle').textContent;el('quick-toggle').disabled=busy;
    el('refresh').disabled=busy||!data?.enabled||!data?.service_conditions?.internet_available;
    el('quick-refresh').disabled=el('refresh').disabled;
    el('report-save').disabled=busy||!data?.enabled;el('pick').disabled=!data?.enabled||!map;
    const currentRevision=(data?.call_assessments||[]).find(item=>item.call_id===el('address-call').value)?.address?.revision;
    const staleRevision=addressReviewRevision===null||currentRevision!==addressReviewRevision;
    el('address-revision').textContent=currentRevision==null?'当前通话地址修订信息尚不可用，请更新记录。':staleRevision?'通话已更新，重新载入地址后再核实。重新载入将替换尚未保存的地址、坐标和核查说明。':`正在核查通话修订 ${addressReviewRevision}；提交时会核对该修订仍然有效。`;
    el('address-revision').classList.toggle('geo-stale-revision',staleRevision);
    el('address-form').querySelectorAll('input,textarea,select').forEach(input=>{input.disabled=busy;});
    el('address-form').querySelectorAll('button').forEach(button=>{button.disabled=busy;});
    el('address-reload').disabled=busy||!data?.enabled||!el('address-call').value;
    el('address-save').disabled=busy||!data?.enabled||!el('address-call').value||staleRevision;
    el('geocode').disabled=busy||!data?.enabled||!el('address-call').value||staleRevision||!el('geocode-consent').checked||!data?.service_conditions?.internet_available;
    el('address-pick').disabled=busy||!data?.enabled||!map;
    el('address-clear').disabled=busy||!data?.enabled||!el('address-call').value;
    el('providers').querySelectorAll('input').forEach(input=>{input.disabled=busy;});
    el('basemap').disabled=!data?.enabled||!data?.service_conditions?.internet_available||!data?.service_conditions?.map_available;
    gpsControls();
  }
  function initMap(){
    if(map||!data||!section.classList.contains('active'))return;if(!window.L){el('map').textContent='地图库不可用，仍可查看下面的位置和来源记录。';return;}
    map=L.map(el('map'),{zoomControl:true,minZoom:5,maxZoom:18}).setView([34.1,-118.2],9);
    boundary=L.geoJSON(data.scope.boundary,{style:{color:'#597e70',weight:1.5,fillColor:'#d6e5df',fillOpacity:.3},interactive:false}).addTo(map);
    layers={device:L.layerGroup().addTo(map),reports:L.layerGroup().addTo(map),official:L.layerGroup().addTo(map),calls:L.layerGroup().addTo(map)};
    map.fitBounds(boundary.getBounds(),{padding:[16,16],animate:false});lastRender='';
    map.attributionControl.addAttribution('<a href="https://arcgis.gis.lacounty.gov/arcgis/rest/services/DRP/ZNET_Public/MapServer/0" target="_blank" rel="noopener noreferrer">County boundary © LA County GIS</a>');
    map.on('click',event=>{if(!picking)return;const prefix=picking==='address'?'address-':'';el(prefix+'lat').value=event.latlng.lat.toFixed(6);el(prefix+'lon').value=event.latlng.lng.toFixed(6);const was=picking;cancelPicking();say(was==='address'?'已填入报告地址坐标；地图选点不构成位置验证，请核查后确认。':'已填入所选事件坐标，请写明来电报告和核查依据后保存。');});
  }
  function updateTiles(){
    const allowed=data?.enabled&&data?.service_conditions?.internet_available&&data?.service_conditions?.map_available&&section.classList.contains('active');
    if(!allowed)el('basemap').checked=false;
    if(map&&el('basemap').checked&&!tiles){tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,keepBuffer:0,updateWhenIdle:true,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · <a href="https://www.openstreetmap.org/fixthemap">Report a map issue</a>'}).addTo(map);tiles.on('tileerror',()=>{el('map-note').textContent='街道图块未能加载；县界与已保存标记仍可用。可取消街道底图，稍后重试。';});}
    if(tiles&&!el('basemap').checked){map.removeLayer(tiles);tiles=null;}
  }
  function p(parent,value){if(value){const n=document.createElement('p');n.textContent=value;if(String(value).length>500){const d=document.createElement('details'),s=document.createElement('summary');s.textContent='展开来源详情 / 原文';d.append(s,n);parent.append(d);}else parent.append(n);}}
  function a(parent,title,url){try{const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password)return;const n=document.createElement('a');n.textContent=title;n.href=u.href;n.target='_blank';n.rel='noopener noreferrer';parent.append(n);}catch(_){}}
  function button(parent,title,fn){const b=document.createElement('button');b.type='button';b.className='ghost';b.textContent=title;b.onclick=fn;parent.append(b);}
  function cancelPicking(){picking=null;el('pick').textContent='在地图上选事件地点';el('address-pick').textContent='在地图上选报告地址';}
  function choosePoint(kind){const next=picking===kind?null:kind;cancelPicking();picking=next;if(next)el(next==='address'?'address-pick':'pick').textContent='取消选点';say(next==='address'?'请在地图上点击本次通话报告的地址；这不会使用设备 GPS。':next==='report'?'请在地图上点击来电者报告的事件地点。':'已取消选点。');}
  function fillAddress(callId){
    if(callId)el('address-call').value=callId;lastAddressCall=el('address-call').value;
    const assessment=(data?.call_assessments||[]).find(item=>item.call_id===lastAddressCall),address=assessment?.address||{};
    addressReviewRevision=Number.isInteger(address.revision)?address.revision:null;
    el('address-label').value=address.display_label||address.candidates?.find(item=>!item.negated&&!item.historical)?.quote||'';
    el('address-lat').value=address.coordinates?.lat??'';el('address-lon').value=address.coordinates?.lon??'';el('address-accuracy').value=address.coordinates?.accuracy_m??'';
    el('address-note').value='';el('address-confirmed').checked=false;el('geocode-consent').checked=false;el('geocode-results').replaceChildren();
    renderGeocode(data?.address_geocodes?.[lastAddressCall]);controls();
  }
  function openAddress(callId){fillAddress(callId);el('address-details').open=true;el('address-details').scrollIntoView({behavior:'smooth',block:'start'});el('address-label').focus({preventScroll:true});}
  function renderGeocode(result){
    el('geocode-results').replaceChildren();if(!result)return;
    if(result.revision!=null&&result.revision!==addressReviewRevision){p(el('geocode-results'),'该查询来自较早的通话修订，不能直接选入当前核查表单；请基于最新原话重新查询。');return;}
    const matches=result.matches||[];
    p(el('geocode-results'),result.status==='no_match'?'未找到匹配地址。请补充门牌、街道与城市，或人工核查后填写坐标。':`${matches.length} 个 Census 地址候选。选择候选只填入表单；仍需人工核对后确认。`);
    for(const match of matches){const item=document.createElement('div');item.className='geo-geocode-match';p(item,match.label);p(item,`${Number(match.lat).toFixed(6)}, ${Number(match.lon).toFixed(6)} · 地址地理编码 / 非实测`);button(item,'选入核查表单',()=>{el('address-label').value=match.label;el('address-lat').value=match.lat;el('address-lon').value=match.lon;el('address-accuracy').value='';el('address-confirmed').checked=false;say('已选入候选坐标；请核对地点、填写核查人和依据后保存确认。');});el('geocode-results').append(item);}
  }
  function markerIcon(status,level){
    const shape=status==='HUMAN_CONFIRMED'?'confirmed':status==='CONFLICT'?'conflict':'candidate';
    const icon=document.createElement('span');icon.className='geo-address-marker '+shape;icon.style.setProperty('--risk-colour',riskColours[level]||riskColours.UNKNOWN);if(shape==='conflict')icon.textContent='×';
    return L.divIcon({className:'geo-address-icon',html:icon.outerHTML,iconSize:[24,24],iconAnchor:[12,12],popupAnchor:[0,-12]});
  }
  function renderAssessments(){
    el('assessments').replaceChildren();if(layers)layers.calls.clearLayers();
    const items=data?.call_assessments||[];
    if(!data.enabled){el('assessments').textContent='插件关闭时不展示地址与区域判断。';el('assessment-count').textContent='';return;}
    if(!items.length){el('assessments').textContent='暂无通话地址判断。新增通话或更新记录后，可在这里逐条核查；没有地址的通话仍会列出。';el('assessment-count').textContent='';return;}
    let mapped=0;
    for(const item of items){
      const address=item.address||{},exposure=item.exposure||{},level=riskColours[exposure.level]?exposure.level:'UNKNOWN',coordinates=address.coordinates;
      const hasCoordinates=coordinates&&Number.isFinite(coordinates.lat)&&Number.isFinite(coordinates.lon)&&Math.abs(coordinates.lat)<=90&&Math.abs(coordinates.lon)<=180;
      const article=document.createElement('article');article.className='geo-card geo-assessment';article.dataset.callId=item.call_id;
      const title=document.createElement('h3');title.textContent=item.call_id;article.append(title);
      const tags=document.createElement('div');tags.className='geo-assessment-tags';const status=document.createElement('span');status.className='geo-tag';status.textContent=addressNames[address.status]||address.status||'待判断';
      const risk=document.createElement('span');risk.className='geo-risk-tag';risk.style.setProperty('--risk-colour',riskColours[level]);risk.textContent=`区域背景：${riskNames[level]} / ${level}`;tags.append(status,risk);article.append(tags);
      p(article,address.display_label||'尚无可用的报告地点。');
      p(article,hasCoordinates?`${coordinates.lat.toFixed(5)}, ${coordinates.lon.toFixed(5)} · ${describe(coordinates.source)||'坐标来源待核实'}${coordinates.accuracy_m!=null?' · 已记录误差范围 ±'+coordinates.accuracy_m+' m':''}`:'未放置地图标记：没有可用坐标，不使用城市中心或设备位置代替。');
      p(article,'地址识别准确率：未实测；人工确认、坐标来源和误差范围分别记录。');
      if(address.verification?.confirmed)p(article,`人工确认：${address.verification.reviewer||'核查人未记录'} · ${date(address.verification.confirmed_at)}${address.verification.stale?' · 通话已更新，需要重新核查':''}`);
      for(const reason of address.reasons||[])p(article,'地址依据：'+reason);
      if(address.flags?.length)p(article,'需核查：'+address.flags.map(describe).join('；'));
      if(address.missing_fields?.length)p(article,'缺失项：'+address.missing_fields.map(describe).join('；'));
      if(address.candidates?.length){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='查看地址候选原话与来源';details.append(summary);for(const candidate of address.candidates){p(details,`“${candidate.quote||''}” · ${describe(candidate.kind)||'地点表述'} · 修订 ${candidate.revision??'未知'} · ${describe(candidate.source)||'通话'}${candidate.negated?' · 否定表述，不作为当前地址':''}${candidate.historical?' · 历史地点，不作为当前地址':''}${candidate.uncertain?' · 表述不确定':''}${candidate.approximate?' · 仅大致位置':''}${candidate.reported?' · 转述，未经独立核实':''}`);}article.append(details);}
      p(article,'区域关系：'+(exposure.label||exposure.relation||'尚无足够来源判断'));
      if(exposure.relation&&exposure.label)p(article,'匹配关系：'+describe(exposure.relation));
      for(const match of exposure.matches||[]){const matchNode=document.createElement('div');matchNode.className='geo-exposure-match';p(matchNode,`${match.title||match.event_id} · ${hazardNames[match.hazard_type]||match.hazard_type||'事件'} · ${riskNames[match.level]||match.level||'未知'}`);p(matchNode,`${describe(match.source_kind)||'来源待核查'} · ${describe(match.relation)||'空间关系未明'}${match.stale?' · 来源过时':''}`);if(match.reported_level&&match.reported_level!==match.level)p(matchNode,'来源原始等级映射：'+match.reported_level+'；当前显示等级已受确定性、时效或有效性限制。');p(matchNode,match.reason);if(match.source_url)a(matchNode,'核对事件原始来源 ↗',match.source_url);article.append(matchNode);}
      const gaps=exposure.gaps||[];if(gaps.length){const box=document.createElement('details');box.className='geo-coverage-gaps';const summary=document.createElement('summary');summary.textContent=`覆盖与不确定性（${gaps.length} 项）`;box.append(summary);gaps.forEach(gap=>p(box,describe(gap)));article.append(box);}
      if(exposure.as_of)p(article,'判断时间 '+date(exposure.as_of));
      p(article,item.call_priority?`宿主提供的独立评分（仅展示）：${item.call_priority.category} · ${item.call_priority.score??'—'} 分`:'宿主未提供通话评分；地图插件不计算通话优先级。');
      const popup=article.cloneNode(true),actions=document.createElement('div');actions.className='geo-actions';article.append(actions);
      if(hasCoordinates&&map){mapped++;const marker=L.marker([coordinates.lat,coordinates.lon],{icon:markerIcon(address.status,level),title:`${item.call_id} · ${addressNames[address.status]||address.status} · ${riskNames[level]}`,keyboard:true}).bindPopup(popup);if(el('layer-calls').checked)marker.addTo(layers.calls);
        if(el('layer-calls').checked&&Number.isFinite(coordinates.accuracy_m)&&coordinates.accuracy_m>0)L.circle([coordinates.lat,coordinates.lon],{radius:coordinates.accuracy_m,color:riskColours[level],weight:1,dashArray:'3 5',fillOpacity:.04}).addTo(layers.calls);
        button(actions,'在地图查看',()=>{el('layer-calls').checked=true;marker.addTo(layers.calls);map.setView([coordinates.lat,coordinates.lon],14);marker.openPopup();el('map').scrollIntoView({behavior:'smooth',block:'center'});});
      }else if(hasCoordinates)mapped++;
      button(actions,'核查 / 修改地址',()=>openAddress(item.call_id));el('assessments').append(article);
    }
    el('assessment-count').textContent=`${items.length} 个通话 · ${mapped} 个有坐标 · ${items.length-mapped} 个待定位`;
  }
  function record(kind,title,tag,lines,source,geometry,action){
    const article=document.createElement('article');article.className='geo-card';const badge=document.createElement('span');badge.className='geo-tag '+kind;badge.textContent=tag;const h=document.createElement('h3');h.textContent=title;article.append(badge,h);lines.forEach(v=>p(article,v));if(source)a(article,'查看原始来源 ↗',source);
    const popup=article.cloneNode(true),actions=document.createElement('div');actions.className='geo-actions';article.append(actions);
    if(geometry&&map){
      const key=kind==='report'?'reports':kind;
      const layer=L.geoJSON(geometry,{style:{color:colours[kind],weight:2,fillOpacity:.13},pointToLayer:(_,ll)=>L.circleMarker(ll,{radius:7,color:'#fff',weight:2,fillColor:colours[kind],fillOpacity:.95})});layer.bindPopup(popup);
      if(el('layer-'+key).checked)layer.addTo(layers[key]);
      button(actions,'在地图查看',()=>{el('layer-'+key).checked=true;layer.addTo(layers[key]);const bounds=layer.getBounds();map.fitBounds(bounds,{maxZoom:14,padding:[30,30]});layer.openPopup();el('map').scrollIntoView({behavior:'smooth',block:'center'});});
    }
    if(action)button(actions,action.label,action.run);el('records').append(article);
  }
  function point(lon,lat){return {type:'Point',coordinates:[lon,lat]};}
  function renderRecords(){
    if(layers)Object.values(layers).forEach(layer=>layer.clearLayers());el('records').replaceChildren();
    renderAssessments();
    if(!data.enabled){el('records').textContent='插件已关闭。开启后查看位置、人工报告和官方事件。';el('count').textContent='';return;}
    for(const item of data.caller_locations){
      record('device',item.call_id,`${item.stale?'旧位置 · ':''}设备授权定位（未经独立验证）`,[
        `${item.lat.toFixed(5)}, ${item.lon.toFixed(5)} · 浏览器报告精度 ±${Math.round(item.accuracy_m)} m`,
        '获取时间 '+date(item.captured_at),item.inside_county?'坐标点在县界内；精度范围可能跨界。':'县界外设备位置；区域事件图层仍仅覆盖 LA County。','单次位置，不代表设备现在仍在此处；不是报告事件地点。'],null,point(item.lon,item.lat),{label:'删除设备位置',run:()=>mutate('caller-location/'+encodeURIComponent(item.call_id),undefined,'DELETE')});
      if(map&&el('layer-device').checked)L.circle([item.lat,item.lon],{radius:item.accuracy_m,color:colours.device,weight:1,fillOpacity:.07}).addTo(layers.device);
    }
    for(const item of data.reports){
      const expiry=item.zone_expires_at||item.valid_until,expired=item.expired||Boolean(expiry&&Date.parse(expiry)<=Date.now()),hasZone=item.reviewed&&Number(item.zone_radius_m)>0;
      record('report',item.label,`${item.synthetic?'合成演示 · ':''}${expired?'已到期 · ':item.stale?'来源过时 · ':''}${item.reviewed?'人工已核查 / 非官方确认':'人工报告 / 待核实'}`,[`关联通话 ${item.call_id} · ${item.lat.toFixed(5)}, ${item.lon.toFixed(5)} · ${hazardNames[item.hazard_type]||'其他事件'}`,item.note,hasZone?`人工核查范围：${item.zone_radius_m} m · ${riskNames[item.zone_level]||item.zone_level} · 虚线圆 / 非官方警戒区`:'报告点，没有确认的影响区域。',expiry?'范围到期 '+date(expiry):'','记录时间 '+date(item.created_at),item.inside_county?'坐标位于县界内。':'报告位于 LA County 以外。'],item.source_url,point(item.lon,item.lat),{label:'移除报告标记',run:()=>mutate('reports/'+encodeURIComponent(item.id),undefined,'DELETE')});
      if(hasZone&&map&&el('layer-reports').checked){const circle=L.circle([item.lat,item.lon],{radius:Number(item.zone_radius_m),color:expired||item.stale?riskColours.UNKNOWN:riskColours[item.zone_level]||riskColours.UNKNOWN,weight:2,dashArray:'7 6',fillOpacity:(expired||item.stale)?0.02:0.08});const popup=document.createElement('div');p(popup,item.label);p(popup,`人工核查范围 · 非官方警戒区 · 半径 ${item.zone_radius_m} m`);p(popup,expired?'已到期，不作为当前区域依据。':`记录等级：${riskNames[item.zone_level]||item.zone_level} · 到期 ${date(expiry)}`);p(popup,item.note);a(popup,'查看所附证据 ↗',item.source_url);circle.bindPopup(popup).addTo(layers.reports);}
    }
    for(const item of data.official_events){record('official',item.title,`${item.expired?'已到期 · ':item.stale?'缓存过时 · ':''}${item.provider.toUpperCase()} 官方发布`,[item.source_status,item.provider==='nws'?'Severity: '+(item.severity||'Unknown')+' · certainty: '+(item.certainty||'Unknown'):'震中记录并不代表此处受损；也不涵盖县外地震带来的震感。','事件 / 生效 '+date(item.occurred_at),'来源更新 '+date(item.updated_at),item.expires_at?'到期 '+date(item.expires_at):'', '获取时间 '+date(item.fetched_at),item.area_description,item.geometry_note,item.description,item.instruction],item.source_url,item.geometry,!item.geometry&&item.affected_zones?.length?{label:'加载此预警的官方区域',run:()=>mutate('event-geometry',{event_id:item.id})}:null);}
    const count=data.caller_locations.length+data.reports.length+data.official_events.length;el('count').textContent=count+' records';
    if(!count)el('records').textContent='暂无已保存的位置或事件。请授权通话定位、保存人工报告，或刷新官方数据。空白地图不表示该区域安全。';
  }
  function render(){
    if(!data)return;initMap();
    const selectedActive=el('active-call').value;el('active-call').replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='选择活动通话（需宿主先标记）';el('active-call').append(placeholder);for(const call of data.calls.filter(call=>call.active)){const option=document.createElement('option');option.value=call.call_id;option.textContent=call.call_id;el('active-call').append(option);}if(data.calls.some(call=>call.active&&call.call_id===selectedActive))el('active-call').value=selectedActive;
    const prev=el('call').value;el('call').replaceChildren();for(const c of data.calls){const o=document.createElement('option');o.value=c.call_id;o.textContent=c.call_id+(c.input_mode==='replay'?' · 合成回放':'');el('call').append(o);}if(data.calls.some(c=>c.call_id===prev))el('call').value=prev;
    const addressCall=el('address-call').value;el('address-call').replaceChildren();for(const c of data.calls){const option=document.createElement('option');option.value=c.call_id;option.textContent=c.call_id+(c.input_mode==='replay'?' · 合成回放':'');el('address-call').append(option);}if(data.calls.some(c=>c.call_id===addressCall))el('address-call').value=addressCall;
    if(lastAddressCall!==el('address-call').value)fillAddress();
    const policy=data.assessment_policy;el('policy-version').textContent=policy?'地址与区域判断规则版本：'+(typeof policy==='string'?policy:policy.version||policy.policy_version||policy.id||'当前本地规则'):'地址与区域判断使用本地原型规则，未建立实测准确率。';
    el('providers').replaceChildren();for(const provider of data.providers){const box=document.createElement('div');box.className='geo-provider';const label=document.createElement('label');label.className='geo-check';const check=document.createElement('input');check.type='checkbox';check.checked=provider.enabled;check.disabled=busy;check.onchange=()=>mutate('config',{providers:{[provider.id]:check.checked}});const name=document.createElement('span');name.textContent=provider.title;label.append(check,name);box.append(label);const status=document.createElement('strong');status.className=provider.stale?'stale':'';status.textContent=!provider.enabled?'图层停用':provider.status==='not_loaded'?'尚未获取':provider.status==='error'?'获取失败 · 旧缓存不可视为当前状态':provider.stale?'缓存已过时，请刷新':'获取成功 · 不代表全部事件';box.append(status);p(box,'上次成功 '+date(provider.last_success_at));p(box,'最近尝试 '+date(provider.last_attempt_at));p(box,provider.error);a(box,'数据源与覆盖说明',provider.source_url);el('providers').append(box);}
    updateTiles();controls();const signature=JSON.stringify([data.enabled,data.caller_locations,data.reports,data.official_events,data.call_assessments]);if(signature!==lastRender){lastRender=signature;renderRecords();}
  }
  async function load(){try{data=await request('state');render();}catch(e){say('无法更新本地地图状态：'+e.message,true);}}
  async function mutate(path,body,method){if(busy)return null;busy=true;controls();try{data=await request(path,body,method);render();say(path==='refresh'?'官方来源检查完成。请查看各来源状态、时间与覆盖范围。':path==='address/geocode'?'地址查询完成，请查看候选结果；查询结果还需要人工核查。':'地图设置或记录已更新。');return data;}catch(e){say(e.message,true);return null;}finally{busy=false;controls();}}
  el('show-map').onclick=()=>el('map').scrollIntoView({behavior:'smooth',block:'center'});el('toggle').onclick=()=>{gpsGeneration++;cancelPicking();void mutate('config',{enabled:!data.enabled});};el('refresh').onclick=()=>mutate('refresh',{});el('reload').onclick=load;
  el('quick-toggle').onclick=()=>el('toggle').click();el('quick-refresh').onclick=()=>el('refresh').click();
  el('fit').onclick=()=>{if(map)map.fitBounds(boundary.getBounds());};el('basemap').onchange=updateTiles;
  for(const key of ['device','reports','official','calls'])el('layer-'+key).onchange=renderRecords;
  el('pick').onclick=()=>choosePoint('report');el('address-pick').onclick=()=>choosePoint('address');
  el('zone-radius').oninput=()=>{const hasZone=el('zone-radius').value.trim()!=='';el('source').required=hasZone;el('reviewed').required=hasZone;el('zone-minutes').required=hasZone;};
  el('report-form').onsubmit=async event=>{event.preventDefault();const radius=el('zone-radius').value.trim();await mutate('reports',{call_id:el('call').value,lat:Number(el('lat').value),lon:Number(el('lon').value),label:el('label').value.trim(),note:el('note').value.trim(),source_url:el('source').value.trim(),reviewed:el('reviewed').checked,hazard_type:el('hazard').value,...(radius?{zone_radius_m:Number(radius),zone_level:el('zone-level').value,valid_minutes:Number(el('zone-minutes').value)}:{})});};
  el('address-call').onchange=()=>{cancelPicking();fillAddress();};
  el('address-reload').onclick=()=>{cancelPicking();fillAddress();say('已载入当前通话修订，请重新核查地址、坐标与依据。');};
  el('geocode-consent').onchange=controls;
  el('geocode').onclick=async()=>{if(el('geocode').disabled)return;const address=el('address-label').value.trim();if(!address){say('请先填写要发送的报告地址。',true);el('address-label').focus();return;}const callId=el('address-call').value;const updated=await mutate('address/geocode',{call_id:callId,address,revision:addressReviewRevision,consent:true});if(updated&&el('address-call').value===callId)renderGeocode(updated.geocode_result||updated.address_geocodes?.[callId]);};
  el('address-form').onsubmit=async event=>{event.preventDefault();if(el('address-save').disabled)return;const accuracy=el('address-accuracy').value.trim();const updated=await mutate('address/confirm',{call_id:el('address-call').value,revision:addressReviewRevision,label:el('address-label').value.trim(),lat:Number(el('address-lat').value),lon:Number(el('address-lon').value),reviewer:el('address-reviewer').value.trim(),note:el('address-note').value.trim(),confirmed:el('address-confirmed').checked,...(accuracy?{accuracy_m:Number(accuracy)}:{})});if(updated){el('address-confirmed').checked=false;say('人工地址确认已保存。地图显示地址核查状态和独立的区域背景；请查看来源与缺失项。');}};
  el('address-clear').onclick=async()=>{const callId=el('address-call').value;if(!callId)return;const updated=await mutate('address/'+encodeURIComponent(callId),undefined,'DELETE');if(updated)fillAddress(callId);};
  el('consent').onchange=()=>{gpsGeneration++;gpsControls();};
  el('locate').onclick=async()=>{
    const id=currentCall();if(el('locate').disabled||!id)return;
    if(!navigator.geolocation){el('gps-message').textContent='当前浏览器不支持定位；通话仍可继续。';return;}
    const generation=++gpsGeneration;gpsBusy=true;gpsControls();el('gps-message').textContent='等待浏览器定位授权……';
    try{
      const pos=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:15000,maximumAge:0}));
      if(generation!==gpsGeneration||currentCall()!==id||!el('consent').checked||!data?.enabled){el('gps-message').textContent='通话或授权状态已变化，本次位置未保存。';return;}
      const payload={call_id:id,lat:pos.coords.latitude,lon:pos.coords.longitude,accuracy_m:pos.coords.accuracy,captured_at:new Date(pos.timestamp).toISOString(),consent:true};
      data=await request('caller-location',payload);render();el('gps-message').textContent=`已保存本次设备位置，精度约 ±${Math.round(pos.coords.accuracy)} m。可在地图卡片删除；需要更新时再次点击定位。`;
    }catch(e){el('gps-message').textContent=({1:'定位权限被拒绝；通话不受影响，可使用人工报告地点。',2:'暂时无法获取设备位置；通话不受影响。',3:'定位超时；通话不受影响，可稍后重试。'})[e.code]||'定位未保存：'+e.message;}finally{gpsBusy=false;gpsControls();}
  };
  el('active-call').onchange=()=>{gpsGeneration++;el('consent').checked=false;gpsControls();};
  document.getElementById('host-call-form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;const payload={call_id:form.elements.call_id.value.trim(),revision:Number(form.elements.revision.value),text:form.elements.text.value,language:form.elements.language.value,input_mode:'host'};const updated=await mutate('calls',payload);if(updated)document.getElementById('host-message').textContent='已保存完整通话文本，修订 '+payload.revision+'。活动状态需由宿主另行设置。';};
  const visibility=new MutationObserver(()=>{if(!section.classList.contains('active'))updateTiles();});visibility.observe(section,{attributes:true,attributeFilter:['class']});
  setInterval(()=>{gpsControls();if(!document.hidden&&(section.classList.contains('active')||currentCall())&&!busy&&!gpsBusy)void load();},5000);
  void load();
})();
