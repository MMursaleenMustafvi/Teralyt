const px=c=>c*1.5+(c>=5?.4:0),py=r=>r*1.5,plotCenter=i=>({x:px(i%10)+.5,y:py(Math.floor(i/10))+.5});
function Iso(svg,o={}){
const S=Object.assign({th:.5,tilt:.55,zoom:innerWidth<700?1.1:1.25,layer:'cls',sel:null,auto:false,drag:true,onpick:null,fx:7.45,fy:5.1,anim:true},o);
const W=14.9,H=8.5;let t0=performance.now(),dn=0,vis=true;
const hex=(h,f)=>'#'+[1,3,5].map(i=>Math.max(0,Math.min(255,Math.round(parseInt(h.substr(i,2),16)*f))).toString(16).padStart(2,'0')).join('');
function P(x,y,z){const dx=x-S.fx,dy=y-S.fy,c=Math.cos(S.th),s=Math.sin(S.th),rx=dx*c-dy*s,ry=dx*s+dy*c,u=34*S.zoom;return[500+rx*u,320+ry*S.tilt*u-z*u*(1.1-S.tilt*.5),ry]}
const pts=a=>a.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');
function flat(x,y,w,d,z,col,extra=''){return`<polygon points="${pts([[x,y],[x+w,y],[x+w,y+d],[x,y+d]].map(p=>P(p[0],p[1],z)))}" fill="${col}" ${extra}/>`}
function box(x,y,w,d,z0,h,col,top){const c4=[[x,y],[x+w,y],[x+w,y+d],[x,y+d]],b=c4.map(p=>P(p[0],p[1],z0)),t=c4.map(p=>P(p[0],p[1],z0+h)),cX=(b[0][0]+b[2][0])/2,cY=(b[0][1]+b[2][1])/2;let s='';
for(let i=0;i<4;i++){const j=(i+1)%4,mx=(b[i][0]+b[j][0])/2-cX,my=(b[i][1]+b[j][1])/2-cY;if(my<=0)continue;const l=Math.hypot(mx,my)||1,f=.72+.28*((-mx/l)*.6+(my/l)*.4);s+=`<polygon points="${pts([b[i],b[j],t[j],t[i]])}" fill="${hex(col,f)}"/>`}
return s+`<polygon points="${pts(t)}" fill="${hex(top||col,1.06)}"/>`}
const dep=(x,y)=>P(x,y,0)[2];
function tree(x,y,T){const a=P(x,y,0),b=P(x,y,.5+.03*Math.sin(T*2+x)),r=7.5*S.zoom;return{d:a[2],s:`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="#5a3d22" stroke-width="${2*S.zoom}"/><circle cx="${b[0]}" cy="${b[1]-r*.5}" r="${r}" fill="#3a8a4c"/><circle cx="${b[0]-r*.3}" cy="${b[1]-r*.8}" r="${r*.6}" fill="#5cae62"/>`}}
const ease=x=>1-Math.pow(1-x,3);
function draw(){const T=(performance.now()-t0)/1000,rise=S.anim?Math.min(1,T/1.8):1,F=[],O=[];
const col={cls:{High:'#3fae5f',Medium:'#e0a93a',Low:'#c9573f'},stat:{Available:'#4fbf86',Reserved:'#e0a93a',Sold:'#c9573f',Unknown:'#9a9078'}};
const wv=S.anim?(T*2.4)%18:-9;
PLOTS.forEach((p,i)=>{const c=i%10,r=Math.floor(i/10),x=px(c),y=py(r),sel=S.sel===p.id,k=S.anim?ease(Math.max(0,Math.min(1,rise*1.6-(c+r)/22))):1,sc=S.anim&&Math.abs(c+r*.6-wv)<1.2;
let roof=S.layer=='sat'?(p.st=='Available'?'#b8a47e':'#8c6e52'):S.layer=='stat'?col.stat[p.st]:col.cls[p.cls];if(sc)roof=hex(roof,1.3);if(sel)roof='#ffd84d';
F.push(`<g data-id="${p.id}" style="cursor:pointer">${flat(x,y,1,1,0,sc?'#f4e6c3':S.layer=='sat'?'#c9b891':'#e9d9b4',sel?'stroke="#fff" stroke-width="3"':'stroke="#bfa97c" stroke-width="1"')}</g>`);
const h=(p.st=='Sold'?.75+(p.id%3)*.12:p.st=='Reserved'?.4:p.st=='Unknown'?.25:.04)*k+(sc?.1:0);
let s=p.st=='Available'?box(x+.1,y+.1,.8,.8,0,.04,roof):box(x+.14,y+.14,.72,.72,0,h,S.layer=='sat'?'#d8c9a8':'#f1e7d0')+box(x+.1,y+.1,.8,.8,h,.12*k,roof);
if(sel)s+=box(x+.45,y+.45,.1,.1,0,h+.9+.12*Math.sin(T*4),'#ffd84d');
O.push({d:dep(x+.5,y+.5),s:`<g data-id="${p.id}" style="cursor:pointer">${s}</g>`})});
for(let r=0;r<5;r++)for(let c=0;c<9;c++)if((c+r)%2==0)O.push(tree(px(c)+1.25+(c==4?.2:0),py(r)+1.25,T));
F.push(flat(0,H+.35,6.4,2.1,0,'#5fa05a'),flat(2.6,H+.75,2,1.1,0,'#4f9fb0'));
for(let i=0;i<14;i++)O.push(tree(.3+(i*.43)%5.9,H+.5+((i*37)%17)/10,T));
[1.2,1.6,1.1,1.4].forEach((hh,k)=>O.push({d:dep(7.9+k*1.7,H+1.1),s:box(7.2+k*1.7,H+.5,1.6,1.2,0,hh*(S.anim?ease(Math.min(1,rise*1.4)):1),'#d9cdb4','#6b4a2f')}));
O.push({d:dep(6.9,H+.9),s:box(6.5,H+.5,.8,.8,0,.7,'#f1e7d0','#f1e7d0')+box(6.75,H+.75,.3,.3,.7,.35,'#3fae5f')});
O.push({d:-99,s:box(6.2,-.55,.35,.35,0,1.3,'#3a2616')},{d:-99,s:box(8.35,-.55,.35,.35,0,1.3,'#3a2616')});
O.sort((a,b)=>a.d-b.d);
svg.innerHTML=box(-.7,-.7,W+1.4,H+3.2,-.35,.35,'#6b4a2f','#8a6a48')+F.join('')+O.map(o=>o.s).join('')}
if(S.drag){let mv=0,lx,ly;svg.addEventListener('pointerdown',e=>{dn=1;mv=0;lx=e.clientX;ly=e.clientY});
addEventListener('pointermove',e=>{if(!dn)return;const dx=e.clientX-lx,dy=e.clientY-ly;lx=e.clientX;ly=e.clientY;mv+=Math.abs(dx)+Math.abs(dy);S.th+=dx*.008;S.tilt=Math.max(.3,Math.min(.9,S.tilt+dy*.003));draw()});
addEventListener('pointercancel',()=>{dn=0});addEventListener('pointerup',e=>{if(dn&&mv<5&&S.onpick){const el=document.elementFromPoint(e.clientX,e.clientY),g=el&&el.closest&&el.closest('[data-id]');if(g)S.onpick(+g.dataset.id)}dn=0});
svg.addEventListener('wheel',e=>{e.preventDefault();S.zoom=Math.max(.6,Math.min(3,S.zoom*(e.deltaY<0?1.1:.9)));draw()},{passive:false})}
if(window.IntersectionObserver)new IntersectionObserver(e=>{vis=e[0].isIntersecting;if(vis)draw()}).observe(svg);
if(S.auto||S.anim)setInterval(()=>{if(document.hidden||!vis)return;if(S.auto&&!dn)S.th+=.004;draw()},45);
svg.setAttribute('viewBox',innerWidth<700?'70 30 860 540':'0 0 1000 620');draw();return{S,draw,restart:()=>{t0=performance.now()}}}
