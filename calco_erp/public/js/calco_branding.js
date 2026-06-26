(function () {
  if (window.__calcoBrandingInitialized) {
    return;
  }
  window.__calcoBrandingInitialized = true;

  const ERP_TITLE = "Calco PolyTechnik Pvt Ltd ERP";
  const LOGIN_TITLE = "Calco PolyTechnik Pvt Ltd Manufacturing ERP";
  const FAVICON_URL = "/assets/calco_erp/images/calco-polytechnik-favicon.svg";
  let scheduled = false;

  function isLoginPage() {
    return document.body?.classList.contains("for-login") || !!document.querySelector(".for-login");
  }

  function setFavicon() {
    let favicon = document.querySelector("link[rel='icon']");
    if (!favicon) {
      favicon = document.createElement("link");
      favicon.rel = "icon";
      document.head.appendChild(favicon);
    }
    if (favicon.href !== window.location.origin + FAVICON_URL) {
      favicon.href = FAVICON_URL;
      favicon.type = "image/svg+xml";
    }
  }

  function setDocumentTitle() {
    const isLogin = isLoginPage();
    const nextTitle = isLogin ? LOGIN_TITLE : ERP_TITLE;
    if (document.title !== nextTitle) {
      document.title = nextTitle;
    }
  }

  function brandLoginCard() {
    if (!isLoginPage()) return;

    const loginHead = document.querySelector(".for-login .page-card-head");
    if (!loginHead) return;

    const heading = loginHead.querySelector("h4");
    if (heading && heading.textContent !== LOGIN_TITLE) {
      heading.textContent = LOGIN_TITLE;
    }

    if (!loginHead.querySelector(".calco-login-subtitle")) {
      const subtitle = document.createElement("div");
      subtitle.className = "calco-login-subtitle";
      subtitle.textContent = "Calco PolyTechnik Pvt Ltd ERP";
      loginHead.appendChild(subtitle);
    }
  }


  function loadProductionConsumptionScript() {
    if (window.__productionConsumptionEntryLoaded) return;

    window.__productionConsumptionEntryLoaded = true;
    const script = document.createElement("script");
    script.src = "/assets/calco_erp/js/production_consumption_entry.js?v=20260625_pce_rm_link_validated";
    script.async = false;
    document.head.appendChild(script);
  }

  function scheduleProductionConsumptionScriptLoad() {
    loadProductionConsumptionScript();
    if (!window.__productionConsumptionEntryLoaded) {
      window.setTimeout(loadProductionConsumptionScript, 1000);
    }
  }
  function applyBranding() {
    scheduled = false;
    setFavicon();
    setDocumentTitle();
    brandLoginCard();
    scheduleProductionConsumptionScriptLoad();
  }

  function scheduleApply() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(applyBranding);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleApply, { once: true });
  } else {
    scheduleApply();
  }

  window.addEventListener("load", scheduleApply, { once: true });
  document.addEventListener("page-change", scheduleApply);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      scheduleApply();
    }
  });

  if (window.frappe && frappe.router && typeof frappe.router.on === "function") {
    frappe.router.on("change", scheduleApply);
  }
})();
