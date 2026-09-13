/* 静态演示层的"假后端"：把网页里的 /api/* 请求映射到同目录下预先导出的 JSON。
 *
 * 这个文件只在 `python webui.py --export <目录>` 生成的静态站点里出现，用来把网页挂到
 * GitHub Pages 这类只能放静态文件、没有 Python 进程的托管上。
 *
 * 能看：构建时离线生成好的每一局 trace（地图 / 频道状态表 / 行动日志 / 汇总 / 算法说明），
 *       下拉框切换案例、刷新、改算法参数框都能用。
 * 不能做：生成新案例、离线案例、实机运行、断点单步 —— 那些必须有一个跑着的后端，
 *         所以这里直接把对应的按钮禁用并写明原因。
 */
(function () {
  "use strict";

  const HERE = new URL("./", document.currentScript ? document.currentScript.src : location.href);
  const realFetch = window.fetch ? window.fetch.bind(window) : null;
  if (!realFetch) return;

  const HINT = "这是静态演示页（GitHub Pages）：数据是构建时离线生成好的。";
  const NEED_BACKEND =
      HINT + "「生成新案例 / 离线案例 / 实机运行 / 断点单步」需要后端进程，"
           + "请在本地跑 python webui.py（接模拟器用 python webui.py --run --robot-id <队号>）。";

  // 页面用到的每一个读接口 → 静态文件
  const ROUTES = {
    "/api/algorithms": "api/algorithms.json",
    "/api/traces": "api/traces.json",
    "/api/gate": "api/gate.json",
    "/api/status": "api/status.json",
    "/api/poll": "api/poll.json",
  };

  function fileFor(url) {
    let u;
    try {
      u = new URL(url, location.href);
    } catch (_) {
      return null;
    }
    const path = u.pathname.replace(/\/+$/, "");
    for (const key in ROUTES) {
      if (path === key || path.endsWith(key)) return ROUTES[key];
    }
    if (path.endsWith("/api/trace")) {
      const name = u.searchParams.get("name") || "";
      return name ? "api/trace/" + encodeURIComponent(name) + ".json" : null;
    }
    return null;
  }

  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    if (method !== "GET") throw new Error(NEED_BACKEND);
    const rel = fileFor(url);
    if (!rel) throw new Error(NEED_BACKEND + "（没有这个接口：" + url + "）");
    const resp = await realFetch(new URL(rel, HERE).href, {cache: "no-cache"});
    if (!resp.ok) throw new Error(resp.status + " " + rel);
    return resp;
  };

  /* 没有服务端就没有 SSE 推送：构造即失败，让网页自己退回轮询（轮询也读静态 JSON）。 */
  function OfflineEventSource(url) {
    const self = this;
    this.url = url;
    this.readyState = 0;
    this.onopen = this.onmessage = this.onerror = null;
    this.close = function () { self.readyState = 2; };
    setTimeout(function () {
      self.readyState = 2;
      if (typeof self.onerror === "function") self.onerror({});
    }, 0);
  }
  OfflineEventSource.CONNECTING = 0;
  OfflineEventSource.OPEN = 1;
  OfflineEventSource.CLOSED = 2;
  window.EventSource = OfflineEventSource;

  /* 必须有后端才成立了的那几个控件：禁用 + 悬浮说明，免得点了只看到一句报错。 */
  const NO_BACKEND = ["newsample", "runMock", "runLive", "dbgSave", "dbgNext", "dbgResume", "dbgAbort"];

  function decorate() {
    const live = document.getElementById("live");
    if (live) live.checked = false;                 // 静态数据没有"新数据"可刷，关掉省流量
    for (const id of NO_BACKEND) {
      const el = document.getElementById(id);
      if (el) {
        el.disabled = true;
        el.title = NEED_BACKEND;
      }
    }
    const header = document.querySelector("header");
    if (header && !document.getElementById("staticBanner")) {
      const banner = document.createElement("div");
      banner.id = "staticBanner";
      banner.style.cssText =
          "flex-basis:100%;font-size:12px;color:#92400e;background:#fef3c7;"
        + "border:1px solid #fcd34d;border-radius:6px;padding:6px 10px;margin:2px 0 4px";
      banner.textContent =
          "静态演示页（GitHub Pages）：下面是构建时离线生成的案例，可直接切换查看；"
        + "生成新案例 / 实机运行需要本地运行 python webui.py。";
      header.appendChild(banner);
    }
  }

  // 本文件插在主脚本之前、且在 </body> 附近执行，此时 header/按钮都已经解析出来了
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", decorate);
  else decorate();
})();
