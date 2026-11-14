"""scratch: Google satellite crop with circles from different sources"""
import sys, os, math, json, urllib.request
sys.path.insert(0,"tools")
import emap_plan as E, numpy as np
from PIL import Image, ImageDraw
SC="C:/Users/Taha/AppData/Local/Temp/claude/fca2435633f85eec/b3f74714-4afd-46c5-b421-4bb995ce4986/scratchpad/sat/"
def gtile(x,y,src="google"):
    p=f"{SC}{src}_19_{x}_{y}.png"
    if not os.path.exists(p):
        u={"google":f"https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z=19","esri":f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/19/{y}/{x}"}[src]
        open(p,"wb").write(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read())
    return Image.open(p).convert("RGB")
def crop(lon,lat,half_m,src="google"):
    gx,gy=E.ll_gpx(lon,lat); r=half_m/E.MPP
    tx0,ty0,tx1,ty1=int((gx-r)//256),int((gy-r)//256),int((gx+r)//256),int((gy+r)//256)
    im=Image.new("RGB",((tx1-tx0+1)*256,(ty1-ty0+1)*256))
    for x in range(tx0,tx1+1):
        for y in range(ty0,ty1+1): im.paste(gtile(x,y,src),((x-tx0)*256,(y-ty0)*256))
    return im,tx0*256,ty0*256
if __name__=="__main__":
    lon,lat=float(sys.argv[1]),float(sys.argv[2]); out=sys.argv[3]
    im,ox,oy=crop(lon,lat,70)
    d=ImageDraw.Draw(im)
    for (lo,la,col) in json.loads(sys.argv[4]):
        x,y=E.ll_gpx(lo,la); x-=ox; y-=oy; R=30/E.MPP
        d.ellipse([x-R,y-R,x+R,y+R],outline=col,width=2); d.line([x-8,y,x+8,y],fill=col,width=2); d.line([x,y-8,x,y+8],fill=col,width=2)
    im.save(out)
