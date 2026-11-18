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
      opacity:0.88,line:{width:3,dash:style.dashed?'dash':'solid',color:style.colour},showlegend:style.showLegend!==false,legendgroup:style.legendGroup};
    if (scale) {
      trace.line={width:3,dash:style.dashed?'dash':'solid',color:values,cmin:scale.min,cmax:scale.max,colorscale:state.colour==='excess'?plasma:'Viridis',reversescale:state.colour==='excess',showscale:style.showScale!==false,
        colorbar:{title:{text:state.colour==='excess'?'Haas excess<br>(dB)':'Relative level<br>(dB)'},thickness:17,len:.72,x:1.015,tickformat:'.0f',outlinewidth:0}};
    }
    return trace;
  }
  function scaleFor(state) {
    const scores=data.rays.filter(r=>(!state.hideOpenings || !r.openings.length) && (!state.hideAudience || !r.audience.length) && chosen(r,state)).map(r=>score(r,state)?.value).filter(Number.isFinite);
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
      const hex=f.colour_hex||'#'+f.colour_rgb.map(v=>v.toString(16).padStart(2,'0')).join('').toUpperCase();
      const ease=f.colour_ease??f.colour_rgb[0]+256*f.colour_rgb[1]+65536*f.colour_rgb[2];
      const colourLine=paragraph(fi,`Face colour: ${hex} · RGB (${f.colour_rgb.join(', ')}) · EASE ${ease}.`);
      const swatch=document.createElement('span');swatch.className='colour-swatch';swatch.style.backgroundColor=hex;swatch.setAttribute('aria-label',`Face colour ${hex}`);colourLine.prepend(swatch);
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
  const echoPlot=document.getElementById('echogram-plot');
  const echoBand=document.getElementById('echo-band');
  for(const hz of data.bands)echoBand.add(new Option(hz+' Hz',hz));
  const tagged=ray=>ray.openings.length>0||ray.audience.length>0;
  const echoBands=state=>echoBand.value==='follow'?bandsFor(state):echoBand.value==='study'?data.bands:[Number(echoBand.value)];
  function echoFileName(state,bands) {
    const safe=v=>String(v).normalize('NFKD').replace(/[^A-Za-z0-9_-]+/g,'_').replace(/^_+|_+$/g,'').slice(0,55)||'MPC';
    return [safe(data.title||'MPC'),safe(state.seat),bands.join('-')+'Hz',state.paths,
      state.hideOpenings?'no-openings':'with-openings',state.hideAudience?'no-audience':'with-audience'].join('_').slice(0,190);
  }
  async function renderEchogram(state) {
    const seat=data.seats.find(s=>s.id===state.seat),bands=echoBands(state);
    const pair=data.rays.filter(r=>r.seat===state.seat);
    const reference=pair.filter(r=>r.order===0).sort((a,b)=>a.arrival-b.arrival)[0];
    const eligible=pair.filter(r=>r.order>0&&(!state.hideOpenings||!r.openings.length)&&(!state.hideAudience||!r.audience.length));
    const haas=data.haas,curves=haas.times_ms.map((x,i)=>[x,haas.levels_db[i]]);
    const traces=[],annotations=[],shapes=[],panels=[];
    const gap=bands.length>1 ? .105 : 0,panelHeight=(1-gap*(bands.length-1))/bands.length;
    const filterText=[state.paths==='D'?'D candidates only':'All reflected paths',state.hideOpenings?'openings hidden':'openings shown',state.hideAudience?'audience hidden':'audience shown'].join(' · ');
    const axis=reference?'Delay after direct sound (ms)':'Absolute arrival time (ms)';
    const layout={height:Math.max(450,290*bands.length+170),width:echoPlot.clientWidth,autosize:true,margin:{l:72,r:25,t:100,b:112},paper_bgcolor:'#fff',plot_bgcolor:'#fff',
      title:{text:escape(data.title||'MPC')+' · '+escape(seat.label)+'<br><sup>'+escape(filterText)+'</sup>',font:{size:17},x:.055,xanchor:'left'},
      font:{family:'-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',size:11,color:'#3c535e'},
      legend:{orientation:'h',x:0,yref:'container',y:.025,yanchor:'bottom',font:{size:10}},annotations,shapes};
    const legendSeen=new Set();
    for(const [index,hz]of bands.entries()) {
      const xId=index?'x'+(index+1):'x',yId=index?'y'+(index+1):'y';
      const upper=1-index*(panelHeight+gap),lower=upper-panelHeight;
      const rows=eligible.filter(r=>state.paths!=='D'||r.metrics[hz].zone==='D');
      const yValue=r=>reference?r.metrics[hz].level:r.metrics[hz].absolute;
      const levels=rows.map(yValue).filter(Number.isFinite);
      const bottom=reference?Math.min(-45,...levels.map(v=>v-3)):levels.length?Math.min(...levels)-5:0;
      const top=reference?Math.max(14,...levels.map(v=>v+3)):levels.length?Math.max(...levels)+5:100;
      const times=rows.map(r=>reference?r.delay:r.arrival).filter(Number.isFinite);
      const xmax=reference?Math.max(100,...times.map(t=>t*1.025)):Math.max(1,...times.map(t=>t*1.025));
      layout['xaxis'+(index?index+1:'')]={domain:[0,1],anchor:yId,range:[reference?-1.5:0,xmax],title:{text:index===bands.length-1?axis:''},gridcolor:'#edf1f3',zerolinecolor:'#c0ccd4'};
      layout['yaxis'+(index?index+1:'')]={domain:[lower,upper],anchor:xId,range:[bottom,top],title:{text:reference?'Relative level (dB)':'Saved path level (dB)'},gridcolor:'#edf1f3',zerolinecolor:'#c0ccd4'};
      const assessed=rows.filter(r=>r.metrics[hz].zone==='D'&&!tagged(r));
      const setAside=rows.filter(r=>r.metrics[hz].zone==='D'&&tagged(r));
      const subtitle=reference?`${hz} Hz · ${rows.length} reflected paths · D: ${assessed.length} untagged + ${setAside.length} tagged`:`${hz} Hz · No direct reference; unclassifiable`;
      annotations.push({xref:'paper',yref:'paper',x:0,y:upper,yshift:22,text:escape(subtitle),showarrow:false,xanchor:'left',font:{size:12}});
      if(reference) {
        const shape=(points,colour)=>shapes.push({type:'path',path:'M '+points.map(p=>p[0]+','+p[1]).join(' L ')+' Z',xref:xId,yref:yId,line:{width:0},fillcolor:colour,layer:'below'});
        const left=curves.filter(p=>p[0]<=50),right=curves.filter(p=>p[0]>=50);
        shape([[0,top],[50,top],...left.slice().reverse()],'rgba(236,228,206,.55)');
        shape([[50,bottom],[100,bottom],...right.slice().reverse()],'rgba(231,238,245,.65)');
        shape([[50,top],[100,top],...right.slice().reverse()],'rgba(244,198,197,.55)');
        shapes.push({type:'line',xref:xId,yref:yId,x0:50,x1:50,y0:bottom,y1:top,line:{color:'#8b979e',width:1,dash:'dot'}});
        traces.push({type:'scatter',mode:'lines',x:curves.map(p=>p[0]),y:curves.map(p=>p[1]),xaxis:xId,yaxis:yId,
          line:{color:'#657681',width:1.3},name:'Approximate Haas boundary',legendgroup:'haas',showlegend:index===0,hoverinfo:'skip'});
      }
      for(const isD of [false,true])for(const dashed of [false,true]) {
        const group=rows.filter(r=>(r.metrics[hz].zone==='D')===isD&&tagged(r)===dashed);
        if(!group.length)continue;
        const x=[],y=[],customdata=[],hover=[],sizes=[];
        for(const ray of group) {
          const t=reference?ray.delay:ray.arrival,v=yValue(ray),info=labelFor(ray,{...state,band:String(hz)});
          x.push(t,t,null);y.push(bottom,v,null);customdata.push([ray.id,hz],[ray.id,hz],null);hover.push(info,info,'');sizes.push(0,isD?7:4,0);
        }
        const key=(isD?'D':'other')+(dashed?'-tagged':''),name=(isD?'D candidate':'Other reflection')+(dashed?' · tagged (dashed)':'');
        const colour=isD?'#ba2639':'#247d73';
        traces.push({type:'scatter',mode:'lines+markers',x,y,xaxis:xId,yaxis:yId,customdata,text:hover,
          hovertemplate:'%{text}<extra></extra>',name,legendgroup:key,showlegend:!legendSeen.has(key),
          line:{color:colour,width:1,dash:dashed?'dash':'solid'},marker:{color:colour,size:sizes,symbol:dashed?'diamond-open':'circle'}});
        legendSeen.add(key);
      }
      if(reference)traces.push({type:'scatter',mode:'markers',x:[0],y:[0],xaxis:xId,yaxis:yId,marker:{size:7,color:'#25313c'},
        name:'Direct reference',legendgroup:'direct',showlegend:index===0,hovertemplate:'Direct sound: 0 ms, 0 dB<extra></extra>'});
      const selected=rows.find(r=>r.id===pick.ray);
      if(selected)traces.push({type:'scatter',mode:'markers',x:[reference?selected.delay:selected.arrival],y:[yValue(selected)],xaxis:xId,yaxis:yId,
        marker:{size:13,color:'#047e9b',symbol:'circle-open',line:{width:2}},showlegend:false,customdata:[[selected.id,hz]],hovertemplate:'Selected path<extra></extra>'});
      if(!rows.length)annotations.push({xref:'paper',yref:'paper',x:.5,y:(lower+upper)/2,showarrow:false,
        text:reference?'No reflected paths match these filters.':state.paths==='D'?'D classification unavailable without direct sound.':'No saved reflected paths for this pair.',font:{color:'#697d86'}});
      panels.push({frequency:hz,rayIds:rows.map(r=>r.id),assessedD:reference?assessed.length:null,taggedD:reference?setAside.length:null,referenceRayId:reference?.id??null});
    }
    await Plotly.react(echoPlot,traces,layout,{responsive:true,displaylogo:false,toImageButtonOptions:{format:'png',filename:echoFileName(state,bands),width:1400,height:330*bands.length+190,scale:2}});
    if(!echoPlot._pathBound){echoPlot.on('plotly_click',event=>{
      const info=event.points[0]?.customdata;if(!Array.isArray(info))return;
      const ray=data.rays.find(r=>r.id===info[0]);if(!ray||ray.order===0)return;
      if(!chosen(ray,snapshot()))el.band.value=String(info[1]);
      pick.ray=ray.id;pick.face=null;update();
    });echoPlot._pathBound=true;}
    api.echogram={bands,panels,reference:!!reference,filename:echoFileName(state,bands),filters:filterText};
    document.getElementById('echo-summary').textContent=reference
      ?'Each band uses its own direct arrival as 0 ms and 0 dB. The Haas curve is approximate; counts are individual paths. Tagged paths remain dashed when shown.'
      :'No direct arrival is saved for this source/receiver. Levels and arrival times are absolute; no Haas curve or D classification is applied.';
  }
  api.downloadEchogram=async()=>{
    const button=document.getElementById('echo-download');button.disabled=true;
    try{await api.ready;return await Plotly.downloadImage(echoPlot,{format:'png',filename:api.echogram.filename,width:1400,height:330*api.echogram.bands.length+190,scale:2});}
    finally{button.disabled=false;}
  };
  echoBand.onchange=()=>update();
  document.getElementById('echo-download').onclick=()=>api.downloadEchogram().catch(e=>{document.getElementById('echo-summary').textContent='PNG download failed: '+e.message;});
  api.setEchogramFrequency=value=>{if(value!=='follow'&&value!=='study'&&!data.bands.includes(Number(value)))throw new Error('Frequency not exported');echoBand.value=String(value);return update();};
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
    const solid=visible.filter(r=>!r.openings.length&&!r.audience.length);
    const dashed=visible.filter(r=>r.openings.length||r.audience.length);
    const hasReference=data.rays.some(r=>r.seat===state.seat&&r.order===0);
    const scale=state.colour==='order'||!hasReference?null:scaleFor(state);
    if (state.colour==='order') {
      for (const order of [1,2,3,4]) {
        const ordinary=solid.filter(r=>r.order===order),special=dashed.filter(r=>r.order===order);
        const name=`Order ${order} (${ordinary.length+special.length})`,legendGroup=`order-${order}`;
        if(ordinary.length)traces.push(pathTrace(ordinary,state,{name,colour:colours[order],legendGroup}));
        if(special.length)traces.push(pathTrace(special,state,{name,colour:colours[order],dashed:true,legendGroup,showLegend:!ordinary.length}));
      }
    } else {
      if(solid.length)traces.push(pathTrace(solid,state,{name:`Solid reflections (${solid.length})`,colour:grey},scale));
      if(dashed.length)traces.push(pathTrace(dashed,state,{name:`Opening / audience reflections (${dashed.length})`,colour:grey,dashed:true,showScale:!solid.length},scale));
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
    await renderEchogram(state);
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
    const jobs=[];
    if(plot.isConnected&&plot._fullLayout)jobs.push(Plotly.relayout(plot,{width:plot.clientWidth,height:plot.clientHeight}));
    if(echoPlot.isConnected&&echoPlot._fullLayout)jobs.push(Plotly.relayout(echoPlot,{width:echoPlot.clientWidth}));
    return Promise.all(jobs);
  }).catch(()=>{}),100);});
  el.reset.addEventListener('click',()=>Plotly.relayout(plot,{'scene.camera':camera}));
  installInspector();
  update();
})();
