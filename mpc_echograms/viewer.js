'use strict';
(() => {
  const data = JSON.parse(document.getElementById('reflection-data').textContent);
  const el = Object.fromEntries(['seat','paths','band','colour','hide-openings','hide-audience','room','surfaces','reset'].map(id => [id, document.getElementById(id)]));
  const escape = v => String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;');
  const plot = document.getElementById('plot');
  const colours = ['#252a30','#1677a8','#289567','#df8b21','#9656ad'];
  const grey = '#a0a4ad';
  const plasma = [[0,'#0d0887'],[1/9,'#46039f'],[2/9,'#7201a8'],[3/9,'#9c179e'],[4/9,'#bd3786'],[5/9,'#d8576b'],[6/9,'#ed7953'],[7/9,'#fb9f3a'],[8/9,'#fdca26'],[1,'#f0f921']];
  const camera = {eye:{x:1.45,y:-1.7,z:1.1},up:{x:0,y:0,z:1},projection:{type:'perspective'}};
  const api = window.reflectionViewer = {data,ready:Promise.resolve(),stats:null};
  const pick={ray:null,face:null};
  const mesh=makeMesh(Object.values(data.faces));
  for(const hz of data.bands){const o=document.createElement('option');o.value=hz;o.textContent=hz+' Hz';el.band.appendChild(o);}
  for (const seat of data.seats) {
    const option = document.createElement('option');
    option.value = seat.id;
    option.textContent = seat.label;
    el.seat.appendChild(option);
  }
  const bandsFor = state => state.band === 'study' ? data.bands : [Number(state.band)];
  const inD = (ray,state) => bandsFor(state).some(hz => ray.metrics[hz].zone === 'D');
  const chosen = (ray,state) => ray.order > 0 && (state.paths === 'all' || inD(ray,state));
  const score = (ray,state) => {
    const metric = state.colour === 'excess' ? 'excess' : 'level';
    const values = bandsFor(state).map(hz=>({value:ray.metrics[hz][metric],hz})).filter(x=>Number.isFinite(x.value));
    return values.reduce((a,b)=>!a||b.value>a.value?b:a,null);
  };
  const signed = (number,digits=2) => Number.isFinite(number) ? (number>0?'+':'')+number.toFixed(digits) : 'outside diagram';
  const labelFor = (ray,state) => {
    const text = [`<b>r${ray.id} · order ${ray.order}</b>`,`${Number.isFinite(ray.delay)?ray.delay.toFixed(2)+' ms after direct sound':ray.arrival.toFixed(2)+' ms absolute; no direct reference'}`,ray.faces.map(escape).join(' → ')];
    text.push(ray.openings.length ? '<b>Opening-dependent:</b> '+ray.openings.map(escape).join(', ') : 'Not tagged as an opening path');
    if(ray.audience.length)text.push('<b>Audience:</b> '+ray.audience.join(', '));
    for (const hz of bandsFor(state)) {
      const m = ray.metrics[hz];
      text.push(`${hz} Hz: ${signed(m.level)} dB relative; excess ${signed(m.excess)} dB · ${m.zone}`);
    }
    return text.join('<br>');
  };
  function pathTrace(rays,state,style,scale) {
    const x=[],y=[],z=[],hover=[],values=[],rayIds=[];
    for (const ray of rays) {
      const text=labelFor(ray,state),s=score(ray,state);
      for (const p of ray.points) {x.push(p[0]);y.push(p[1]);z.push(p[2]);hover.push(text);rayIds.push(ray.id);values.push(s?s.value:scale?.min||0);}
      x.push(null);y.push(null);z.push(null);hover.push('');rayIds.push(null);values.push(scale?.min||0);
    }
    const trace={type:'scatter3d',mode:'lines',x,y,z,text:hover,customdata:rayIds,hovertemplate:'%{text}<extra></extra>',name:style.name,
      opacity:style.ghost?0.4:0.88,line:{width:3,dash:style.dashed?'dash':'solid',color:style.colour},showlegend:style.showLegend!==false,legendgroup:style.legendGroup};
    if (scale && !style.ghost) {
      trace.line={width:3,dash:style.dashed?'dash':'solid',color:values,cmin:scale.min,cmax:scale.max,colorscale:state.colour==='excess'?plasma:'Viridis',reversescale:state.colour==='excess',showscale:style.showScale!==false,
        colorbar:{title:{text:state.colour==='excess'?'Haas excess<br>(dB)':'Relative level<br>(dB)'},thickness:17,len:.72,x:1.015,tickformat:'.0f',outlinewidth:0}};
    }
    return trace;
  }
  function scaleFor(state) {
    const scores=data.rays.filter(r=>!r.openings.length && (!state.hideAudience || !r.audience.length) && chosen(r,state)).map(r=>score(r,state)?.value).filter(Number.isFinite);
    if (!scores.length) return {min:0,max:1};
    const min=state.paths==='D'&&state.colour==='excess'?0:Math.floor(Math.min(...scores)/5)*5;
    const max=state.paths==='D'&&state.colour==='excess'?Math.max(1,Math.ceil(Math.max(...scores))):Math.ceil(Math.max(...scores)/5)*5;
    return {min,max:max===min?min+1:max};
  }
  function makeMesh(faces,highlight=false) {
    if(!faces.length)return null;
    const x=[],y=[],z=[],i=[],j=[],k=[],labels=[],facecolor=[];
    for(const f of faces){const start=x.length;for(const p of f.points){x.push(p[0]);y.push(p[1]);z.push(p[2]);labels.push(f.label);}
      for(const t of f.triangles){i.push(start+t[0]);j.push(start+t[1]);k.push(start+t[2]);facecolor.push(highlight?'#eaa73d':`rgb(${f.colour_rgb.join(',')})`);}}
    return {type:'mesh3d',x,y,z,i,j,k,customdata:labels,facecolor,opacity:highlight?.6:.14,
      name:highlight?'Selected faces':'Project surfaces',showlegend:false,flatshading:true,
      hovertemplate:'Project face %{customdata}<extra></extra>',lighting:{ambient:.8,diffuse:.5},showscale:false};
  }
  function addHighlights(traces,visible) {
    const ray=visible.find(r=>r.id===pick.ray);
    if(ray){const pts=ray.points;traces.push({type:'scatter3d',mode:'lines+markers',x:pts.map(p=>p[0]),y:pts.map(p=>p[1]),z:pts.map(p=>p[2]),
      customdata:pts.map(()=>ray.id),line:{color:'#047e9b',width:7},marker:{size:4,color:'#047e9b'},name:`Selected r${ray.id}`,showlegend:false,
      text:pts.map(()=>`r${ray.id}`),hovertemplate:'%{text}<extra></extra>'});}
    const labels=pick.face?[pick.face]:ray?ray.faces:[];
    const selected=makeMesh([...new Set(labels)].map(l=>data.faces[l]).filter(Boolean),true);
    if(selected)traces.push(selected);
  }
  function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.appendChild(p);return p;}
  function updateInspector(state,visible) {
    const selector=document.getElementById('ray-pick');selector.replaceChildren(new Option('Choose a path…',''));
    for(const r of visible)selector.add(new Option(`r${r.id} · order ${r.order} · ${Number.isFinite(r.delay)?r.delay.toFixed(2)+' ms delay':r.arrival.toFixed(2)+' ms absolute'}`,r.id));
    if(!visible.some(r=>r.id===pick.ray))pick.ray=null;
    selector.value=pick.ray??'';
    const ri=document.getElementById('ray-info');ri.replaceChildren();
    const ray=visible.find(r=>r.id===pick.ray);
    if(ray){paragraph(ri,`r${ray.id}: ${ray.faces.join(' → ')}. Saved MPC levels and path; project materials are an unverified snapshot.`);
      const route=document.createElement('div');route.className='route';ri.appendChild(route);
      for(const label of ray.faces){const f=data.faces[label];const b=document.createElement('button');b.textContent=f?`${label} · ${f.material_front}`:`${label} · face unavailable`;b.onclick=()=>{pick.face=label;update();};route.appendChild(b);}
      for(const hz of bandsFor(state)){const m=ray.metrics[hz];paragraph(ri,`${hz} Hz: ${m.absolute.toFixed(2)} dB saved; ${signed(m.level)} dB relative; ${signed(m.excess)} dB above boundary (${m.zone}).`);}}
    const fi=document.getElementById('face-info');fi.replaceChildren();const f=data.faces[pick.face];
    document.getElementById('face-pick').value=f?f.label:'';
    const chart=document.getElementById('material-chart');chart.hidden=true;
    if(f){paragraph(fi,`${f.label} · ${f.area_m2.toFixed(3)} m² · ${f.vertex_ids.length} vertices · normal (${f.normal.map(v=>v.toFixed(4)).join(', ')}).`);
      paragraph(fi,`Project front: ${f.material_front||'unassigned'}; rear: ${f.material_rear||'unassigned'}. Planarity deviation: ${f.planarity_error_m.toExponential(2)} m. These materials are not confirmed as those used by the MPC.`);
      if(f.triangulation_error)paragraph(fi,f.triangulation_error);
      const curves=[];for(const [side,name]of [['Front',f.material_front],['Rear',f.material_rear]]){const m=data.config.materials[name];
        if(!m){paragraph(fi,`${side} material coefficients unavailable in the supplied data.`);continue;}
        paragraph(fi,`${side} coefficient provenance: ${m.source}`);
        for(const key of ['absorption','scattering'])if(m[key])curves.push({x:m.frequencies_Hz,y:m[key],mode:'lines+markers',name:`${side} ${key}`});}
      if(curves.length){chart.hidden=false;Plotly.react(chart,curves,{height:260,margin:{l:45,r:15,t:20,b:60},xaxis:{title:'Frequency (Hz)',type:'log'},yaxis:{title:'Coefficient',range:[0,1]},legend:{orientation:'h'}},{responsive:true,displaylogo:false});}}
  }
  function installInspector() {
    const fs=document.getElementById('face-pick');for(const f of Object.values(data.faces))fs.add(new Option(`${f.label} · ${f.material_front||'unassigned'}`,f.label));
    fs.disabled=!mesh;el.surfaces.disabled=!mesh;
    document.getElementById('ray-pick').onchange=e=>{pick.ray=e.target.value?Number(e.target.value):null;pick.face=null;update();};
    fs.onchange=e=>{pick.face=e.target.value||null;update();};
    document.getElementById('clear-pick').onclick=()=>{pick.ray=null;pick.face=null;update();};
    api.inspectRay=id=>{pick.ray=id;pick.face=null;return update();};api.inspectFace=label=>{pick.face=label;return update();};
    const p=data.project;const banner=document.getElementById('compatibility');
    banner.textContent=p?`${p.face_count} native faces · ${p.vertex_count} vertices · ${p.compatibility.matched_nodes}/${p.compatibility.checked_nodes} sampled reflection nodes match at ${p.compatibility.tolerance_m} m. Project material settings are not verified against the MPC.`:'MPC-only view. No native project face/material data supplied.';
    document.getElementById('project-details').textContent=p?`${p.compatibility.warnings.join(' ')} Geometry not hit by saved paths cannot be validated against the MPC. Material curves shown here, if provided, come from the explicit configuration.`:'Add --project for native room surfaces. Face categories require an explicit --project-config; no openings or audience surfaces are inferred automatically.';
  }
  const roomTrace = {
    type:'scatter3d',mode:'lines',name:'Room outline',showlegend:false,hoverinfo:'skip',
    x:[],y:[],z:[],line:{color:'#c0ccd4',width:1},opacity:.5
  };
  for (const [a,b] of data.edges) {
    roomTrace.x.push(a[0],b[0],null);roomTrace.y.push(a[1],b[1],null);roomTrace.z.push(a[2],b[2],null);
  }
  function snapshot() {
    return {seat:el.seat.value,paths:el.paths.value,band:el.band.value,colour:el.colour.value,
            hideOpenings:el['hide-openings'].checked,hideAudience:el['hide-audience'].checked,room:el.room.checked,surfaces:el.surfaces.checked};
  }
  async function render() {
    const state=snapshot(),seat=data.seats.find(s=>s.id===state.seat);
    const rays=data.rays.filter(r=>r.seat===state.seat && chosen(r,state));
    const opening=rays.filter(r=>r.openings.length),audience=rays.filter(r=>r.audience.length);
    const visible=rays.filter(r=>(!state.hideOpenings||!r.openings.length)&&(!state.hideAudience||!r.audience.length));
    const physical=visible.filter(r=>!r.openings.length),visibleOpening=visible.filter(r=>r.openings.length);
    const traces=[];
    if(el.surfaces.checked && mesh)traces.push(mesh);
    if (state.room) traces.push(roomTrace);
    const solid=physical.filter(r=>!r.audience.length);
    const dashed=physical.filter(r=>r.audience.length);
    const hasReference=data.rays.some(r=>r.seat===state.seat&&r.order===0);
    const scale=state.colour==='order'||!hasReference?null:scaleFor(state);
    if(visibleOpening.length)traces.push(pathTrace(visibleOpening,state,{name:`Opening-dependent (${visibleOpening.length})`,colour:grey,ghost:true,dashed:true}));
    if (state.colour==='order') {
      for (const order of [1,2,3,4]) {
        const ordinary=solid.filter(r=>r.order===order),special=dashed.filter(r=>r.order===order);
        const name=`Order ${order} (${ordinary.length+special.length})`,legendGroup=`order-${order}`;
        if(ordinary.length)traces.push(pathTrace(ordinary,state,{name,colour:colours[order],legendGroup}));
        if(special.length)traces.push(pathTrace(special,state,{name,colour:colours[order],dashed:true,legendGroup,showLegend:!ordinary.length}));
      }
    } else {
      if(solid.length)traces.push(pathTrace(solid,state,{name:`Solid reflections (${solid.length})`,colour:grey},scale));
      if(dashed.length)traces.push(pathTrace(dashed,state,{name:`Audience reflections (${dashed.length})`,colour:grey,dashed:true,showScale:!solid.length},scale));
    }
    const direct=data.rays.find(r=>r.seat===state.seat&&r.order===0);
    if (direct) {
      const points=direct.points;
      traces.push({type:'scatter3d',mode:'lines',name:'Direct reference',x:points.map(p=>p[0]),y:points.map(p=>p[1]),z:points.map(p=>p[2]),
        line:{color:'#1f2933',width:3,dash:'dash'},hovertemplate:'Direct sound reference<extra></extra>'});
    }
    const positions=[seat.source.position,seat.position];
    traces.push({type:'scatter3d',mode:'markers+text',name:'Source / listener',showlegend:false,
      x:positions.map(p=>p[0]),y:positions.map(p=>p[1]),z:positions.map(p=>p[2]),text:[escape(seat.source.label),escape(seat.label)],textposition:'top center',
      marker:{size:5,color:['#202b35','#168a77']},hovertemplate:'%{text}<br>X %{x:.2f} · Y %{y:.2f} · Z %{z:.2f} m<extra></extra>'});
    const layout={paper_bgcolor:'#ffffff',autosize:true,width:plot.clientWidth,height:plot.clientHeight,margin:{l:0,r:state.colour==='order'?0:88,t:12,b:55},uirevision:'ae-room',
      font:{family:'-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',color:'#3c535e',size:12},
      showlegend:true,legend:{orientation:'h',x:.02,y:-.02,font:{size:11},itemclick:false,itemdoubleclick:false},
      scene:{uirevision:'ae-room',aspectmode:'data',dragmode:'turntable',camera,
        ...Object.fromEntries(['x','y','z'].map((a,i)=>[a+'axis',{title:{text:a.toUpperCase()+' (m)'},range:data.limits[i],showbackground:false,gridcolor:'#e6edef',zerolinecolor:'#c8d3d7',tickfont:{size:10}}]))}};
    addHighlights(traces,visible);
    await Plotly.react(plot,traces,layout,{responsive:true,displaylogo:false,scrollZoom:true,modeBarButtonsToRemove:['resetCameraLastSave3d','hoverClosest3d']});
    if(!plot._inspectBound){plot.on('plotly_click',event=>{const id=event.points[0]?.customdata;if(typeof id==='number'){pick.ray=id;pick.face=null;}else if(typeof id==='string'&&data.faces[id])pick.face=id;else return;update();});plot._inspectBound=true;}
    const physicalD=data.rays.filter(r=>r.seat===state.seat&&r.order>0&&!r.openings.length&&(!state.hideAudience||!r.audience.length)&&inD(r,state));
    const visibleIds=[...physical,...visibleOpening].map(r=>r.id);
    api.stats={state,selected:rays.length,physical:physical.length,openingSelected:opening.length,openingVisible:visibleOpening.length,
      visible:visibleIds.length,classifiable:hasReference,physicalD:hasReference?physicalD.length:null,visibleRayIds:visibleIds,physicalRayIds:physical.map(r=>r.id),scale,
      audienceSelected:audience.length,audienceVisible:visible.filter(r=>r.audience.length).length,directReferenceId:direct?.id??null};
    document.getElementById('stat-total').textContent=api.stats.visible;
    document.getElementById('stat-physical').textContent=physical.length;
    document.getElementById('stat-opening').textContent=`${visibleOpening.length} / ${opening.length}`;
    document.getElementById('stat-audience').textContent=`${api.stats.audienceVisible} / ${audience.length}`;
    document.getElementById('stat-D').textContent=hasReference?physicalD.length:'—';
    document.getElementById('view-title').textContent=`${seat.label}`;
    const bandNote=state.band==='study'?data.bands.join(' / ')+' Hz':state.band+' Hz';
    const metricNote=state.colour==='order'?'Colours show the number of reflections.':state.colour==='level'
      ?`Colours show ${state.band==='study'?'the highest relative level across the selected bands':'level relative to this listener’s direct sound'}.`
      :`Colours show ${state.band==='study'?'the largest Haas-boundary excess across the selected bands':'excess above the Haas boundary'}. Positive excess is D only after 50 ms.`;
    document.getElementById('colour-note').textContent=hasReference?metricNote:'No direct reference; unclassifiable. Relative dB colours are unavailable; geometry is shown without a level scale.';
    document.getElementById('status').textContent=`${bandNote} · ${state.paths==='D'?'D candidates only':'All saved reflected paths'} · ${state.hideOpenings?'Opening-dependent paths hidden':'Opening-dependent paths shown dashed'} · ${state.hideAudience?'Audience reflections hidden':'Audience reflections shown dashed'}`;
    document.getElementById('empty').hidden=api.stats.visible!==0;
    updateInspector(state,visible);
    plot.setAttribute('aria-label',`${seat.label}: ${api.stats.visible} visible reflected paths; ${physical.length} from physical surfaces.`);
    return api.stats;
  }
  function update() {
    api.ready=api.ready.then(render).catch(error=>{document.getElementById('status').textContent='Could not render the selected view: '+error.message;throw error;});
    return api.ready;
  }
  api.setState=async values=>{
    for(const [key,value] of Object.entries(values)) {
      const id=key==='hideOpenings'?'hide-openings':key==='hideAudience'?'hide-audience':key;
      if(!el[id])throw new Error('Unknown control '+key);
      if(el[id].type==='checkbox')el[id].checked=Boolean(value);else el[id].value=String(value);
    }
    return update();
  };
  for(const id of ['seat','paths','band','colour','hide-openings','hide-audience','room','surfaces'])el[id].addEventListener('change',update);
  let resize;
  window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(()=>api.ready.then(()=>{
    if(plot.isConnected&&plot._fullLayout)return Plotly.relayout(plot,{width:plot.clientWidth,height:plot.clientHeight});
  }).catch(()=>{}),100);});
  el.reset.addEventListener('click',()=>Plotly.relayout(plot,{'scene.camera':camera}));
  installInspector();
  update();
})();
