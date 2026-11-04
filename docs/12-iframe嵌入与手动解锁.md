# 第 12 步：付费后没解锁 —— 原因与两条出路

## 发生了什么

真钱支付成功了，Stripe 把浏览器送回：

```
https://contractredline.io/?session_id=cs_live_a146vUO294RCnaf4wTM0SzN5OxtOeAydidhiB2ibzoZNOP4J!X0a8s1
```

但那个页面是我们自己的域名，Streamlit 应用是以 **iframe** 嵌在里面的。
`?session_id=` 挂在外层地址栏上，iframe 内部的应用读不到 —— `st.query_params`
只能看到 iframe 自己的地址，而那个地址上什么都没有。

顺带说明为什么不是别的原因：如果是密钥模式不对（测试密钥验正式订单），页面上
会有一条红色的 `Stripe has no record of that checkout`。付款后页面**完全没报错、
只是回到上传界面**，正是因为应用压根没拿到订单号，连验证都没发起。

## 现在：三条取号路径，按顺序尝试

改在 `app/web/paywall.py`：

1. **应用自己的地址栏** —— 直接部署时就是这条，和以前一样。
2. **`Referer` 请求头** —— iframe 场景下，外层页面的地址会随 iframe 请求发给
   服务器，能从中捞出 `session_id`。不需要 JavaScript，不需要改 Cloudflare 页面，
   命中就自动解锁。
3. **手动粘贴**（页面上的 `Already paid? Unlock with your Stripe receipt`）——
   前两条都没命中时永远可用。粘贴整条跳转链接或那串 `cs_live_...` 即可。

三条路最后都走同一个服务端校验 `billing.verify_session()`：订单必须是
`status=complete`、`payment_status=paid`、金额 ≥ $1。所以“粘贴”这条路并不会
降低安全性 —— 能被相信的理由自始至终只有 Stripe 的回复，不是浏览器。

## 可选：让第 2 条也稳定命中（改 Cloudflare 页面，10 秒）

如果 Referer 被浏览器策略剥掉，可以在 Cloudflare 那个包装页里，把外层查询串
补到 iframe 的 src 上。把 `你的应用地址` 换成真实域名（例如
`https://xxx.streamlit.app`）：

```html
<iframe id="cr-app" src="https://你的应用地址" style="..."></iframe>
<script>
  (function () {
    var app = document.getElementById("cr-app");
    if (app && window.location.search) {
      // 把 ?session_id=... 带到 iframe 里面去
      app.src = "https://你的应用地址/" + window.location.search;
    }
  })();
</script>
```

只做这一件事：有查询串时重新赋一次 src。不要做定时器、不要在 iframe 加载后再改，
否则会把应用刷掉。

## 一个必须知道的限制（不是 bug）

没数据库，所以付款成功回到网站时，那份合同的结果**已经不在**了：需要重新上传
同一个文件，20 张卡片立刻全开，不会二次扣费。这是“坚决不上数据库”的直接代价，
你在接受付费墙方案时已经确认过。

另外：**同一笔订单只能开一份报告**。粘贴第二次会被拒绝并提示“这笔付款已经开过
一份报告”，防止一条回执链接变成无限次使用。
