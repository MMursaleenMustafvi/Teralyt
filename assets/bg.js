document.addEventListener('DOMContentLoaded',()=>{
const fx=document.createElement('div');fx.className='bgfx';const cv=document.createElement('canvas');fx.appendChild(cv);document.body.prepend(fx);
const g=document.createElement('canvas');g.width=g.height=160;const gx=g.getContext('2d'),im=gx.createImageData(160,160);for(let i=0;i<im.data.length;i+=4){const v=Math.random()*255;im.data[i]=v;im.data[i+1]=v*.85;im.data[i+2]=v*.65;im.data[i+3]=Math.random()*46}gx.putImageData(im,0,0);fx.style.setProperty('--grain','url('+g.toDataURL()+')');
const x=cv.getContext('2d'),RM=matchMedia('(prefers-reduced-motion: reduce)').matches,rnd=(a,b)=>a+Math.random()*(b-a);
let W,H,D,sky,L,F,Lv,Du,bl,mist;
const glow=document.createElement('canvas');glow.width=glow.height=48;{const c=glow.getContext('2d'),r=c.createRadialGradient(24,24,0,24,24,24);r.addColorStop(0,'rgba(240,255,160,1)');r.addColorStop(.25,'rgba(190,240,110,.55)');r.addColorStop(1,'rgba(190,240,110,0)');c.fillStyle=r;c.fillRect(0,0,48,48)}
function init(){D=Math.min(devicePixelRatio||1,1.5);W=innerWidth;H=innerHeight;cv.width=W*D;cv.height=H*D;x.setTransform(D,0,0,D,0,0);
sky=x.createLinearGradient(0,0,0,H);sky.addColorStop(0,'#04100a');sky.addColorStop(.4,'#0a2015');sky.addColorStop(.72,'#17250f');sky.addColorStop(1,'#2a190c');
L=[{b:.6,a:.07,s:.5,c1:'#10301f',c2:'#0a1c12',f:[2.1,4.3,7.7]},{b:.69,a:.06,s:.8,c1:'#163a25',c2:'#0d2418',f:[1.7,3.9,6.1]},{b:.79,a:.05,s:1.1,c1:'#432b14',c2:'#24160a',f:[2.6,5.2,8.3]},{b:.9,a:.035,s:1.5,c1:'#2a190a',c2:'#150c05',f:[3.1,6.1,9.7]}];
L.forEach((l,i)=>{l.ph=i*2.3;const q=x.createLinearGradient(0,H*(l.b-l.a*2),0,H);q.addColorStop(0,l.c1);q.addColorStop(1,l.c2);l.g=q});
F=Array.from({length:Math.min(46,Math.max(18,Math.round(W/22)))},()=>({x:rnd(0,W),y:rnd(H*.3,H*.95),ph:rnd(0,6.3),sp:rnd(.8,2),r:rnd(.6,1.3),a:rnd(0,6.3),v:rnd(.1,.4)}));
Lv=Array.from({length:Math.round(Math.min(16,W/90))},()=>({x:rnd(0,W),y:rnd(-H,H),s:rnd(5,11),r:rnd(0,6.3),rv:rnd(-.02,.02),vy:rnd(.3,.75),sw:rnd(0,6.3),sa:rnd(.5,1.4),c:['#4a8a3e','#7f9433','#a0702c','#6e4220','#2f6a3f'][Math.floor(rnd(0,5))]}));
Du=Array.from({length:60},()=>({x:rnd(0,W),y:rnd(0,H),r:rnd(.5,1.6),v:rnd(.1,.35),s:rnd(0,6),c:['227,207,165','185,116,63'][Math.floor(rnd(0,2))],a:rnd(.1,.3)}));
bl=Array.from({length:Math.round(W/9)},(_,i)=>({x:i*9+rnd(-4,4),h:rnd(24,80),ph:rnd(0,6.3),c:Math.random()<.5?'#0d2a18':'#16401f',w:rnd(2.5,4.5)}));
mist=[0,1,2].map(i=>({y:H*(.56+i*.11),sp:7+i*5,o:rnd(0,W),w:W*.8,a:.09-i*.015}))}
const hy=(l,xx,t,sc)=>H*l.b+H*l.a*(Math.sin(xx*.0021*l.f[0]+t*.12*l.s+l.ph+sc*.0008*l.s)+.6*Math.sin(xx*.0021*l.f[1]-t*.15*l.s+l.ph*1.3)+.3*Math.sin(xx*.0021*l.f[2]+t*.09+l.ph));
function hill(l,t,sc){x.fillStyle=l.g;x.beginPath();x.moveTo(0,H);for(let xx=0;xx<=W+12;xx+=12)x.lineTo(xx,hy(l,xx,t,sc));x.lineTo(W+12,H);x.fill()}
function frame(ts){const t=ts/1000,sc=scrollY;x.globalCompositeOperation='source-over';x.fillStyle=sky;x.fillRect(0,0,W,H);
x.globalCompositeOperation='lighter';for(let i=0;i<4;i++){const a=.07+.05*Math.sin(t*.45+i*1.7),ox=W*(.72+.06*Math.sin(t*.25+i))+i*50,sw=Math.sin(t*.3+i*2)*70,q=x.createLinearGradient(0,0,0,H);q.addColorStop(0,`rgba(255,205,120,${a})`);q.addColorStop(1,'rgba(255,205,120,0)');x.fillStyle=q;x.beginPath();x.moveTo(ox,-40);x.lineTo(ox+110,-40);x.lineTo(ox-W*.5+i*150+sw+190,H);x.lineTo(ox-W*.5+i*150+sw-90,H);x.fill()}
x.globalCompositeOperation='source-over';hill(L[0],t,sc);hill(L[1],t,sc);
mist.forEach(m=>{const mx=((t*m.sp+m.o)%(W+m.w*2))-m.w;x.save();x.translate(mx+m.w/2,m.y);x.scale(m.w/200,.5);const q=x.createRadialGradient(0,0,0,0,0,200);q.addColorStop(0,`rgba(190,215,170,${m.a})`);q.addColorStop(1,'rgba(190,215,170,0)');x.fillStyle=q;x.fillRect(-200,-200,400,400);x.restore()});
hill(L[2],t,sc);
x.globalCompositeOperation='lighter';F.forEach(f=>{f.a+=.004;f.x+=Math.cos(f.a*1.3)*.35+f.v*.3;f.y+=Math.sin(f.a)*.3;if(f.x>W+20)f.x=-20;if(f.x<-20)f.x=W+20;if(f.y>H)f.y=H*.4;if(f.y<H*.2)f.y=H*.9;x.globalAlpha=Math.max(0,.25+.75*(.5+.5*Math.sin(t*f.sp+f.ph)));const s=22*f.r;x.drawImage(glow,f.x-s/2,f.y-s/2,s,s)});x.globalAlpha=1;x.globalCompositeOperation='source-over';
hill(L[3],t,sc);
bl.forEach(b=>{const y0=hy(L[3],b.x,t,sc)+3,sw=Math.sin(t*1.3+b.ph+b.x*.004)*b.h*.25+Math.sin(t*.4+b.x*.002)*b.h*.18;x.fillStyle=b.c;x.beginPath();x.moveTo(b.x-b.w/2,y0);x.quadraticCurveTo(b.x+sw*.35,y0-b.h*.6,b.x+sw,y0-b.h);x.quadraticCurveTo(b.x+sw*.35+b.w*.4,y0-b.h*.55,b.x+b.w/2,y0);x.fill()});
Lv.forEach(l=>{l.y+=l.vy;l.sw+=.02;l.x+=Math.sin(l.sw)*l.sa;l.r+=l.rv;if(l.y>H+20){l.y=-20;l.x=rnd(0,W)}x.save();x.translate(l.x,l.y);x.rotate(l.r);x.scale(Math.cos(l.sw*.8),1);x.globalAlpha=.8;x.fillStyle=l.c;x.beginPath();x.moveTo(0,-l.s);x.quadraticCurveTo(l.s*.8,0,0,l.s);x.quadraticCurveTo(-l.s*.8,0,0,-l.s);x.fill();x.strokeStyle='rgba(0,0,0,.3)';x.beginPath();x.moveTo(0,-l.s);x.lineTo(0,l.s);x.stroke();x.restore()});
Du.forEach(q=>{q.y-=q.v;q.s+=.01;q.x+=Math.sin(q.s)*.35;if(q.y<-5){q.y=H+5;q.x=rnd(0,W)}x.fillStyle=`rgba(${q.c},${q.a})`;x.beginPath();x.arc(q.x,q.y,q.r,0,6.283);x.fill()})}
init();let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(init,150)});
if(RM)frame(0);else(function lp(ts){if(!document.hidden)frame(ts);requestAnimationFrame(lp)})(0)});
