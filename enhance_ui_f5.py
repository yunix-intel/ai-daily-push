#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase F5: UI/UX 优化脚本
在现有 finance_dashboard.html 基础上添加：
1. 浮动导航栏（主导航 + 子导航）
2. 返回顶部按钮
3. 要闻折叠展开功能
4. 响应式优化
"""

import re

def enhance_html():
    """读取并增强 HTML 文件"""

    with open('finance_dashboard.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. 修改 scroll-padding-top
    html = html.replace(
        'html{scroll-behavior:smooth}',
        'html{scroll-behavior:smooth;scroll-padding-top:120px}'
    )

    # 2. 在 @media 之前添加新样式
    new_styles = """  .nav{position:sticky;top:0;z-index:1000;background:rgba(14,16,20,.92);border-bottom:1px solid var(--border);backdrop-filter:blur(8px)}
  .nav-main{display:flex;gap:8px;padding:10px 0;overflow-x:auto;scrollbar-width:none}
  .nav-main::-webkit-scrollbar{display:none}
  .nav-main a{padding:8px 14px;border-radius:8px;font-size:14px;font-weight:500;white-space:nowrap;transition:all .2s;border:1px solid transparent}
  .nav-main a:hover{background:var(--card);border-color:var(--accent)}
  .nav-main a b{margin-left:4px;color:var(--accent2);font-size:13px}
  .nav-sub{display:flex;gap:6px;padding:8px 0;border-top:1px solid var(--border);overflow-x:auto;scrollbar-width:none}
  .nav-sub::-webkit-scrollbar{display:none}
  .nav-label{font-size:13px;color:var(--muted);padding:4px 8px;white-space:nowrap}
  .nav-sub a{padding:4px 10px;border-radius:6px;font-size:13px;white-space:nowrap;transition:all .2s;background:var(--chip)}
  .nav-sub a:hover{background:var(--accent);color:white}
  .card.hidden{display:none}
  .toggle-btn-wrap{text-align:center;margin-top:16px}
  .toggle-btn{padding:10px 24px;border-radius:8px;background:var(--card);color:var(--text);border:1px solid var(--border);cursor:pointer;font-size:14px;font-weight:500;transition:all .2s;font-family:inherit}
  .toggle-btn:hover{background:var(--card-hover);border-color:var(--accent)}
  .toggle-btn:active{transform:scale(.98)}
  .back-to-top{position:fixed;bottom:30px;right:30px;width:48px;height:48px;border-radius:50%;background:var(--accent);color:white;border:none;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.3);transition:all .3s;opacity:0;visibility:hidden;z-index:999;display:flex;align-items:center;justify-content:center}
  .back-to-top.show{opacity:1;visibility:visible}
  .back-to-top:hover{transform:translateY(-4px);box-shadow:0 6px 20px rgba(0,0,0,.4)}
  .back-to-top:active{transform:translateY(-2px)}
  @media (max-width:768px){.nav-main{padding:8px 0;gap:6px}.nav-main a{padding:6px 10px;font-size:13px}.nav-sub{padding:6px 0}.nav-sub a{padding:4px 8px;font-size:12px}.back-to-top{bottom:20px;right:20px;width:44px;height:44px}.toggle-btn{padding:8px 20px;font-size:13px}}
  @media (max-width:560px){.hero{padding:22px 0 12px}.grid{grid-template-columns:1fr}.nav-main a{font-size:12px;padding:5px 8px}.nav-sub{font-size:11px}.back-to-top{width:42px;height:42px}}
"""

    html = html.replace(
        '  @media (max-width:560px){.hero{padding:22px 0 12px}.grid{grid-template-columns:1fr}}',
        new_styles
    )

    # 3. 修改导航结构
    html = html.replace(
        '<nav class="nav"><div class="wrap" id="navLinks"></div></nav>',
        '<nav class="nav"><div class="wrap"><div class="nav-main" id="navLinks"></div><div class="nav-sub" id="navSub" style="display:none"></div></div></nav>'
    )

    # 4. 添加返回顶部按钮
    back_to_top_btn = '''<button class="back-to-top" id="backToTop" title="返回顶部">
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="18 15 12 9 6 15"></polyline>
  </svg>
</button>
'''

    html = html.replace(
        '<footer><div class="wrap">',
        back_to_top_btn + '<footer><div class="wrap">'
    )

    # 5. 增强 JavaScript - 找到脚本开始位置
    # 修改导航生成逻辑
    old_nav_code = "  let nav='<a href=\"#domestic-section\">国内要闻<b>'+meta.domesticCount+'</b></a><a href=\"#intl-section\">国际要闻<b>'+meta.internationalCount+'</b></a>';\n  document.getElementById('navLinks').innerHTML=nav;"

    new_nav_code = """  let navMain='<a href=\"#top\">📊 行情</a>';
  if((domestic.emergencyEvents||[]).length>0||(international.emergencyEvents||[]).length>0){navMain+='<a href=\"#breaking-section\">🔥 突发</a>';}
  navMain+='<a href=\"#domestic-section\">🇨🇳 国内<b>'+meta.domesticCount+'</b></a>';
  navMain+='<a href=\"#intl-section\">🌍 国际<b>'+meta.internationalCount+'</b></a>';
  if(strategy&&strategy.suggestion){navMain+='<a href=\"#strategyBlock\">📈 策略</a>';}
  document.getElementById('navLinks').innerHTML=navMain;
  let navSubLinks=[];
  if(domestic.sections){domestic.sections.forEach((s,i)=>{navSubLinks.push('<a href=\"#domestic-sec-'+i+'\">'+s.label+'</a>');});}
  if(international.sections){international.sections.forEach((s,i)=>{navSubLinks.push('<a href=\"#intl-sec-'+i+'\">'+s.label+'</a>');});}
  if(navSubLinks.length>0){document.getElementById('navSub').innerHTML='<span class=\"nav-label\">板块：</span>'+navSubLinks.join('');document.getElementById('navSub').style.display='flex';"""

    html = html.replace(old_nav_code, new_nav_code)

    # 6. 修改 renderMarket 函数以支持折叠
    # 找到 sections.forEach 部分并替换
    old_section_loop = "    sections.forEach((s,i)=>{html+='<section class=\"section\" id=\"'+marketId+'-sec-'+i+'\">"

    new_section_loop = """    const INITIAL_ITEMS=6;
    sections.forEach((s,i)=>{
      const totalItems=s.items.length;
      const showToggle=totalItems>INITIAL_ITEMS;
      html+='<section class=\"section\" id=\"'+marketId+'-sec-'+i+'\">"
"""

    html = html.replace(old_section_loop, new_section_loop)

    # 修改卡片渲染，添加隐藏类
    old_card_loop = "      s.items.forEach(it=>{"
    new_card_loop = """      s.items.forEach((it,idx)=>{
        const isHidden=showToggle&&idx>=INITIAL_ITEMS;"""

    html = html.replace(old_card_loop, new_card_loop)

    old_card_start = "        html+='<article class=\"card\">';"
    new_card_start = "        html+='<article class=\"card'+(isHidden?' hidden':'')+' data-section=\"'+marketId+'-'+i+'\">';"

    html = html.replace(old_card_start, new_card_start)

    # 在 section 结束前添加展开按钮
    old_section_end = "      html+='</div></section>';});"
    new_section_end = """      html+='</div>';
      if(showToggle){
        html+='<div class=\"toggle-btn-wrap\"><button class=\"toggle-btn\" data-target=\"'+marketId+'-'+i+'\" data-state=\"collapsed\">展开更多 ('+(totalItems-INITIAL_ITEMS)+' 条) ▼</button></div>';
      }
      html+='</section>';});"
"""

    html = html.replace(old_section_end, new_section_end)

    # 7. 在脚本末尾添加事件处理代码
    script_end_code = """  document.querySelectorAll('.toggle-btn').forEach(btn=>{
    btn.addEventListener('click',function(){
      const target=this.dataset.target;
      const state=this.dataset.state;
      const cards=document.querySelectorAll('.card[data-section=\"'+target+'\"]');
      if(state==='collapsed'){
        cards.forEach(card=>card.classList.remove('hidden'));
        this.textContent='收起 ▲';
        this.dataset.state='expanded';
      }else{
        cards.forEach((card,idx)=>{if(idx>=6)card.classList.add('hidden');});
        const hiddenCount=cards.length-6;
        this.textContent='展开更多 ('+hiddenCount+' 条) ▼';
        this.dataset.state='collapsed';
        this.closest('.section').scrollIntoView({behavior:'smooth',block:'start'});
      }
    });
  });
  const backBtn=document.getElementById('backToTop');
  if(backBtn){
    window.addEventListener('scroll',()=>{
      if(window.scrollY>600){backBtn.classList.add('show');}else{backBtn.classList.remove('show');}
    });
    backBtn.addEventListener('click',()=>{window.scrollTo({top:0,behavior:'smooth'});});
  }
})();
</script>"""

    html = html.replace('})();\n</script>', script_end_code)

    # 8. 修复 breaking-section ID
    html = html.replace(
        '<div class="block emergency"><h2>🚨 突发事件</h2>',
        '<div class="block emergency" id="breaking-section"><h2>🚨 突发事件</h2>'
    )

    # 写回文件
    with open('finance_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("Phase F5 UI enhancement completed")
    print("   - Floating navigation bar")
    print("   - Back to top button")
    print("   - News collapse/expand")
    print("   - Responsive optimization")


if __name__ == '__main__':
    enhance_html()
