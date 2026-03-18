import logging,asyncio,httpx,json,os,re
from datetime import datetime
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup
from telegram.ext import Application,CommandHandler,MessageHandler,CallbackQueryHandler,filters,ContextTypes
logging.basicConfig(level=logging.WARNING)
TOKEN='8625439097:AAFbb-HoDUd6-VuRhQQ9302hDiEw4mndax0'
OWNER=8628735314
CEX_CI=0.1
DEX_CI=1
AT=0.5
CS=5
DB='/data/data/com.termux/files/home/tokens.json'
mon={}
last_gap={}
gap_history={}
dex_cache={}
def save():
 try:
  d={str(k):{a:{'sym':s.get('sym',''),'paused':s.get('paused',False)} for a,s in v.items()} for k,v in mon.items()}
  open(DB,'w').write(json.dumps(d))
 except:pass
def load():
 try:
  if os.path.exists(DB):
   d=json.loads(open(DB).read())
   for cid,toks in d.items():
    mon[int(cid)]={a:{'sym':s['sym'],'paused':s.get('paused',False),'dp':0,'mp':None,'lp':None,'ts':'offline'} for a,s in toks.items()}
 except:pass
async def gp(client,url):
 try:
  r=await client.get(url,timeout=10)
  if r.status_code==200:return r.json()
 except:pass
 return None
async def get_dex(client,addr):
 try:
  r=await gp(client,'https://api.dexscreener.com/latest/dex/tokens/'+addr)
  if not r:return None
  pairs=[p for p in(r.get('pairs')or[])if p.get('chainId')=='bsc']
  if not pairs:return None
  pairs.sort(key=lambda x:float(x.get('liquidity',{}).get('usd')or 0),reverse=True)
  p=pairs[0]
  return{'sym':p['baseToken']['symbol'],'name':p['baseToken']['name'],'px':float(p.get('priceUsd')or 0)}
 except:return None
async def get_mexc(client,sym):
 try:
  for v in list(dict.fromkeys([sym,sym.upper(),sym.replace('SWAP',''),sym[:5],sym[:4]])):
   for pair in[v+'USDT',v+'USDC']:
    r=await gp(client,'https://api.mexc.com/api/v3/ticker/price?symbol='+pair)
    if r:
     p=float(r.get('price')or 0)
     if p>0:return p
 except:pass
 return None
async def get_lbank(client,sym):
 try:
  variants=list(dict.fromkeys([sym.lower(),sym.lower().replace('swap',''),sym.lower()[:5],sym.lower()[:4],sym.lower()[:3]]))
  for v in[x for x in variants if len(x)>=2]:
   for pair in[v+'_usdt',v+'_usdc']:
    r=await gp(client,'https://api.lbank.info/v2/ticker.do?symbol='+pair)
    if r and r.get('result')=='true':
     items=r.get('data')or[]
     if items:
      p=float(items[0].get('ticker',{}).get('latest')or 0)
      if p>0:return p
 except:pass
 return None
def fp(p):
 if p is None or p==0:return None
 if p<0.000001:return '$%.10f'%p
 if p<0.0001:return '$%.8f'%p
 if p<0.01:return '$%.6f'%p
 if p<1:return '$%.4f'%p
 return '$%.4f'%p
def gg(dp,cp):
 if not dp or not cp or dp==0:return None
 return((cp-dp)/dp)*100
def cl(g):
 if g is None:return''
 if g>0:return'💚'
 if g<0:return'❤️'
 return'⚪'
def ts():return datetime.now().strftime('%H:%M:%S')
def sh(a):return a[:6]+'...'+a[-4:]
def clean_addr(t):return re.sub(r'\s+','',t).strip()
def profit_calc(gap):
 invest=100
 profit=invest*(abs(gap)/100)
 net=profit*0.998
 return '💰 $%.0f invest → $%.2f profit'%(invest,net)
def update_history(key,gap):
 if key not in gap_history:gap_history[key]=[]
 gap_history[key].append((ts(),gap))
 if len(gap_history[key])>5:gap_history[key]=gap_history[key][-5:]
def get_history(key):
 h=gap_history.get(key,[])
 if not h:return''
 lines=['⏰ Gap History:']
 for t,g in reversed(h[-3:]):lines.append('  '+t+' → %.2f%%'%g)
 return'\n'.join(lines)
def should_alert(key,gap):
 last=last_gap.get(key,None)
 if last is None or abs(gap-last)>=AT:
  last_gap[key]=gap
  update_history(key,gap)
  return True
 return False
def fmt_alert(sym,dp,cp,cex_name,gap):
 fire='🔥🔥' if abs(gap)>=5 else '🔥' if abs(gap)>=2 else '🚨'
 direction='💚 BUY DEX → SELL CEX' if gap>0 else '❤️ SELL DEX → BUY CEX'
 key=sym+cex_name
 hist=get_history(key)
 msg=(fire+' Cloud AI PRO ALERT\n'
  +sym+' | '+ts()+'\n'
  +'DEX: '+fp(dp)+'\n'
  +cex_name+': '+(fp(cp) or 'N/A')+'\n'
  +cl(gap)+' GAP: %.2f%%\n'%gap
  +direction+'\n'
  +profit_calc(gap))
 if hist:msg+='\n\n'+hist
 return msg
def bmsg(sym,dp,mp,lp):
 lines=[sym,'DEX: '+(fp(dp) or 'N/A')]
 for nm,cp in[('MEXC',mp),('LBank',lp)]:
  g=gg(dp,cp)
  if cp:lines.append(nm+': '+fp(cp)+(' ('+cl(g)+' %.2f%%)'%g if g else ''))
  else:lines.append(nm+': not listed')
 gaps=[(nm,abs(gg(dp,cp))) for nm,cp in[('MEXC',mp),('LBank',lp)] if cp and gg(dp,cp)]
 if gaps:
  lines.append('--- GAP ---')
  for nm,g in gaps:lines.append(nm+' gap: %.2f%%'%g)
 return'\n'.join(lines)
def mkb():
 return InlineKeyboardMarkup([
  [InlineKeyboardButton('➕ Add Token',callback_data='add'),InlineKeyboardButton('🗑 Delete Token',callback_data='delete')],
  [InlineKeyboardButton('📋 Token List',callback_data='list'),InlineKeyboardButton('📊 Live Status',callback_data='status')],
  [InlineKeyboardButton('⏸ Pause All',callback_data='pause'),InlineKeyboardButton('▶️ Resume All',callback_data='resume')],
  [InlineKeyboardButton('⚙️ Settings',callback_data='settings'),InlineKeyboardButton('❓ Help',callback_data='help')],
 ])
def tkb(addr,paused):
 tl='▶️ Resume' if paused else '⏸ Pause'
 tc=('tr_'+addr) if paused else ('tp_'+addr)
 return InlineKeyboardMarkup([
  [InlineKeyboardButton(tl,callback_data=tc),InlineKeyboardButton('🗑 Delete',callback_data='td_'+addr)],
  [InlineKeyboardButton('🔄 Refresh',callback_data='tf_'+addr)],
  [InlineKeyboardButton('🔙 Menu',callback_data='menu')],
 ])
def lkb(cid):
 t=mon.get(cid,{})
 rows=[[InlineKeyboardButton(('⏸ ' if st.get('paused') else '🟢 ')+st.get('sym','?')+' | '+(fp(st.get('dp',0)) or 'N/A'),callback_data='ti_'+a)] for a,st in t.items()]
 rows.append([InlineKeyboardButton('🔙 Back',callback_data='menu')])
 return InlineKeyboardMarkup(rows)
def hm():
 return('🤖 Cloud AI Ultra-Fast PRO\n\n⚡ CEX Scan: '+str(CEX_CI)+'s\n⚡ DEX Scan: '+str(DEX_CI)+'s\n🔔 Alert: gap >= '+str(AT)+'%\n📡 MEXC | LBank\n💰 Profit Calc ✅\n⏰ Gap History ✅\n🔒 Owner Only ✅\n\n👇 বাটন চাপুন')
def card(addr,st):
 s='⏸ PAUSED' if st.get('paused') else '🟢 ACTIVE'
 return bmsg(st.get('sym','?'),st.get('dp',0),st.get('mp'),st.get('lp'))+'\n'+s+' | '+st.get('ts','offline')
async def dex_loop(client):
 while True:
  try:
   addrs=set(a for toks in mon.values() for a in toks)
   for addr in addrs:
    r=await get_dex(client,addr)
    if r:dex_cache[addr]=r
    await asyncio.sleep(0.1)
  except:pass
  await asyncio.sleep(DEX_CI)
async def cex_loop(app,client):
 while True:
  try:
   tasks=[]
   for cid,toks in list(mon.items()):
    for addr,st in list(toks.items()):
     if not st.get('paused'):tasks.append(check_token(app,client,cid,addr,st))
   if tasks:await asyncio.gather(*tasks,return_exceptions=True)
  except:pass
  await asyncio.sleep(CEX_CI)
async def check_token(app,client,cid,addr,st):
 try:
  cached=dex_cache.get(addr)
  if not cached:return
  sym=cached['sym'];dp=cached['px']
  mp,lp=await asyncio.gather(get_mexc(client,sym),get_lbank(client,sym))
  st.update({'sym':sym,'dp':dp,'mp':mp,'lp':lp,'ts':ts()})
  save()
  for cex_name,cp in[('MEXC',mp),('LBank',lp)]:
   if cp:
    gap=gg(dp,cp)
    if gap is not None and abs(gap)>=AT:
     key=str(cid)+addr+cex_name
     if should_alert(key,gap):
      await app.bot.send_message(cid,fmt_alert(sym,dp,cp,cex_name,gap))
 except:pass
async def loop(app):
 load()
 limits=httpx.Limits(max_connections=100,max_keepalive_connections=50)
 transport=httpx.AsyncHTTPTransport(retries=2)
 async with httpx.AsyncClient(limits=limits,transport=transport,timeout=10) as client:
  await asyncio.gather(dex_loop(client),cex_loop(app,client))
async def start(u,c):
 if u.effective_chat.id!=OWNER:await u.message.reply_text('❌ Access denied!');return
 await u.message.reply_text(hm(),reply_markup=mkb())
async def cb(u,c):
 q=u.callback_query;d=q.data;cid=q.message.chat_id
 if cid!=OWNER:await q.answer('❌ Access denied!',show_alert=True);return
 await q.answer()
 if d=='menu':await q.edit_message_text(hm(),reply_markup=mkb())
 elif d=='add':await q.edit_message_text('➕ BSC address paste করুন:\n0x... (42 chars)',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Cancel',callback_data='menu')]]))
 elif d=='list':
  t=mon.get(cid,{})
  if not t:await q.edit_message_text('📭 কোনো token নেই.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('➕ Add',callback_data='add'),InlineKeyboardButton('🔙',callback_data='menu')]]))
  else:await q.edit_message_text('📋 Tokens: '+str(len(t)),reply_markup=lkb(cid))
 elif d=='delete':
  t=mon.get(cid,{})
  if not t:await q.edit_message_text('📭 কোনো token নেই.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙',callback_data='menu')]]))
  else:await q.edit_message_text('🗑 কোনটা delete করবেন?',reply_markup=lkb(cid))
 elif d=='status':
  t=mon.get(cid,{})
  if not t:await q.answer('📭 নেই!',show_alert=True);return
  for addr,st in t.items():await q.message.reply_text(card(addr,st),reply_markup=tkb(addr,st.get('paused',False)))
 elif d=='pause':
  for st in mon.get(cid,{}).values():st['paused']=True
  save();await q.answer('⏸ সব pause!',show_alert=True)
 elif d=='resume':
  for st in mon.get(cid,{}).values():st['paused']=False
  save();await q.answer('▶️ সব resume!',show_alert=True)
 elif d=='settings':await q.edit_message_text('⚙️ Settings\n⚡ CEX: '+str(CEX_CI)+'s\n⚡ DEX: '+str(DEX_CI)+'s\n🔔 Alert: '+str(AT)+'%\n🔄 Cooldown: '+str(CS)+'s\n📡 MEXC|LBank\n🔒 Owner only ✅',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙',callback_data='menu')]]))
 elif d=='help':await q.edit_message_text('❓ Help\n1. Add BSC address\n2. CEX প্রতি '+str(CEX_CI)+'s check\n3. DEX প্রতি '+str(DEX_CI)+'s check\n4. Gap >= '+str(AT)+'% হলে alert\n5. 💚 BUY DEX → SELL CEX\n6. ❤️ SELL DEX → BUY CEX\n⚠️ BSC only',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙',callback_data='menu')]]))
 elif d.startswith('ti_'):
  addr=d[3:];st=mon.get(cid,{}).get(addr)
  if not st:await q.answer('পাওয়া যায়নি!',show_alert=True);return
  await q.edit_message_text(card(addr,st),reply_markup=tkb(addr,st.get('paused',False)))
 elif d.startswith('tp_'):
  addr=d[3:]
  if addr in mon.get(cid,{}):
   mon[cid][addr]['paused']=True;save()
   await q.answer('⏸ Paused!')
   await q.edit_message_text(card(addr,mon[cid][addr]),reply_markup=tkb(addr,True))
 elif d.startswith('tr_'):
  addr=d[3:]
  if addr in mon.get(cid,{}):
   mon[cid][addr]['paused']=False;save()
   await q.answer('▶️ Resumed!')
   await q.edit_message_text(card(addr,mon[cid][addr]),reply_markup=tkb(addr,False))
 elif d.startswith('td_'):
  addr=d[3:];sym=mon.get(cid,{}).get(addr,{}).get('sym',sh(addr))
  await q.edit_message_text('⚠️ Delete '+sym+'?',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Yes',callback_data='tdo_'+addr),InlineKeyboardButton('❌ No',callback_data='ti_'+addr)]]))
 elif d.startswith('tdo_'):
  addr=d[4:];sym=mon.get(cid,{}).pop(addr,{}).get('sym',sh(addr));save()
  await q.edit_message_text('✅ '+sym+' deleted.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Menu',callback_data='menu')]]))
 elif d.startswith('tf_'):
  addr=d[3:];st=mon.get(cid,{}).get(addr)
  if not st:await q.answer('পাওয়া যায়নি!',show_alert=True);return
  await q.answer('🔄 Refreshing...')
  async with httpx.AsyncClient(timeout=10) as client:
   r=await get_dex(client,addr)
   if r:
    dex_cache[addr]=r
    mp,lp=await asyncio.gather(get_mexc(client,r['sym']),get_lbank(client,r['sym']))
    st.update({'sym':r['sym'],'dp':r['px'],'mp':mp,'lp':lp,'ts':ts()});save()
  await q.edit_message_text(card(addr,st),reply_markup=tkb(addr,st.get('paused',False)))
async def txt(u,c):
 if u.effective_chat.id!=OWNER:await u.message.reply_text('❌ Access denied!');return
 t=clean_addr(u.message.text);cid=u.effective_chat.id
 if not(t.startswith('0x') and len(t)==42):
  await u.message.reply_text('❌ Valid BSC address দিন\n0x... (42 chars)');return
 toks=mon.setdefault(cid,{})
 if t in toks:
  await u.message.reply_text('ℹ️ '+toks[t].get('sym','?')+' already monitored!',reply_markup=tkb(t,toks[t].get('paused',False)));return
 ld=await u.message.reply_text('⏳ Fetching prices...')
 async with httpx.AsyncClient(timeout=10) as client:
  r=await get_dex(client,t)
  if not r:await ld.edit_text('❌ BSC তে পাওয়া যায়নি.');return
  dex_cache[t]=r
  sym=r['sym']
  mp,lp=await asyncio.gather(get_mexc(client,sym),get_lbank(client,sym))
 toks[t]={'sym':sym,'dp':r['px'],'mp':mp,'lp':lp,'paused':False,'ts':ts()}
 save()
 await ld.edit_text('✅ '+sym+' monitoring শুরু!\n\n'+bmsg(sym,r['px'],mp,lp)+'\n\n⚡CEX:'+str(CEX_CI)+'s | DEX:'+str(DEX_CI)+'s | 🔔'+str(AT)+'%',reply_markup=tkb(t,False))
async def pi(app):
 asyncio.create_task(loop(app))
def main():
 app=Application.builder().token(TOKEN).post_init(pi).build()
 app.add_handler(CommandHandler('start',start))
 app.add_handler(CommandHandler('menu',start))
 app.add_handler(CallbackQueryHandler(cb))
 app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,txt))
 print('✅ Cloud AI Ultra-Fast PRO running!')
 app.run_polling(drop_pending_updates=True)
if __name__=='__main__':
 import asyncio
 asyncio.set_event_loop(asyncio.new_event_loop())
 main()
