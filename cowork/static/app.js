/* VIP GROUP COWORK — tương tác nhẹ, không phụ thuộc thư viện ngoài. */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(function () {
    /* ---------- sidebar mobile ---------- */
    var sidebar = document.getElementById("sidebar");
    var scrim = document.querySelector("[data-scrim]");
    var toggle = document.querySelector("[data-toggle-sidebar]");

    function closeSidebar() {
      if (!sidebar) return;
      sidebar.classList.remove("open");
      if (scrim) scrim.hidden = true;
      if (toggle) toggle.setAttribute("aria-expanded", "false");
      document.body.classList.remove("nav-open");
    }
    function openSidebar() {
      if (!sidebar) return;
      sidebar.classList.add("open");
      if (scrim) scrim.hidden = false;
      if (toggle) toggle.setAttribute("aria-expanded", "true");
      document.body.classList.add("nav-open");
    }
    if (toggle) {
      toggle.addEventListener("click", function () {
        if (sidebar && sidebar.classList.contains("open")) closeSidebar();
        else openSidebar();
      });
    }
    if (scrim) scrim.addEventListener("click", closeSidebar);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeSidebar();
    });
    if (sidebar) {
      sidebar.querySelectorAll("a.nav-item").forEach(function (a) {
        a.addEventListener("click", function () {
          if (window.matchMedia("(max-width: 960px)").matches) closeSidebar();
        });
      });
    }

    /* ---------- flash ---------- */
    document.querySelectorAll("[data-flash]").forEach(function (el) {
      var btn = el.querySelector("[data-dismiss]");
      if (btn) btn.addEventListener("click", function () { el.remove(); });
      window.setTimeout(function () {
        el.style.transition = "opacity .3s";
        el.style.opacity = "0";
        window.setTimeout(function () { el.remove(); }, 320);
      }, 9000);
    });

    /* ---------- confirm trước thao tác phá huỷ ---------- */
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        var msg = form.getAttribute("data-confirm") || "Xác nhận thực hiện thao tác này?";
        if (!window.confirm(msg)) e.preventDefault();
      });
    });

    /* ---------- lọc tự động ---------- */
    document.querySelectorAll("form[data-autosubmit]").forEach(function (form) {
      form.querySelectorAll("select").forEach(function (sel) {
        sel.addEventListener("change", function () { form.submit(); });
      });
    });

    /* ---------- sao chép ---------- */
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var sel = btn.getAttribute("data-copy");
        var node = document.querySelector(sel);
        if (!node) return;
        var text = node.textContent || "";
        function done() {
          var old = btn.innerHTML;
          btn.innerHTML = "Đã sao chép";
          window.setTimeout(function () { btn.innerHTML = old; }, 1800);
        }
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(done).catch(function () { fallback(text, done); });
        } else {
          fallback(text, done);
        }
      });
    });
    function fallback(text, done) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.className = "visually-hidden";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
    }

    /* ---------- hiện/ẩn mật khẩu ---------- */
    document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var input = document.querySelector(btn.getAttribute("data-toggle-password"));
        if (!input) return;
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.setAttribute("aria-pressed", show ? "true" : "false");
      });
    });

    /* ---------- chọn tất cả quyền trong một module ---------- */
    document.querySelectorAll("[data-check-all]").forEach(function (master) {
      var scope = document.querySelector(master.getAttribute("data-check-all"));
      if (!scope) return;
      var boxes = Array.prototype.slice.call(scope.querySelectorAll("input[type=checkbox]:not(:disabled)"));
      function sync() {
        var checked = boxes.filter(function (b) { return b.checked; }).length;
        master.checked = checked === boxes.length && boxes.length > 0;
        master.indeterminate = checked > 0 && checked < boxes.length;
      }
      master.addEventListener("change", function () {
        boxes.forEach(function (b) { b.checked = master.checked; });
        sync();
      });
      boxes.forEach(function (b) { b.addEventListener("change", sync); });
      sync();
    });

    /* ---------- vai trò → hiện phạm vi / tổ chức đối tác ---------- */
    document.querySelectorAll("[data-role-select]").forEach(function (select) {
      var scopeBlock = document.querySelector("[data-scope-block]");
      var partnerField = document.querySelector("[data-partner-field]");
      var deptSelect = document.querySelector("[data-dept-select]");
      function sync() {
        var v = select.value;
        if (scopeBlock) scopeBlock.hidden = v !== "admin";
        if (partnerField) partnerField.hidden = v !== "partner";
        if (deptSelect) deptSelect.required = (v === "department_manager" || v === "employee");
      }
      select.addEventListener("change", sync);
      sync();
    });

    /* ---------- kiểm tra kết nối Brain ---------- */
    document.querySelectorAll("[data-brain-test]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var url = btn.getAttribute("data-brain-test");
        var box = document.querySelector("[data-brain-result]");
        if (!url || !box) return;
        btn.disabled = true;
        box.hidden = false;
        box.className = "brain-test-result";
        box.textContent = "Đang kiểm tra…";
        fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
          .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
          .then(function (res) {
            var ok = res.ok && res.body && res.body.ok;
            box.className = "brain-test-result " + (ok ? "ok" : "err");
            var data = (res.body && res.body.data) || {};
            box.textContent = ok
              ? "Kết nối thành công · " + (data.trangThai || "đang sống") + " · " + (data.url || "")
              : "Chưa kết nối: " + (data.thongBao || "không rõ lỗi");
          })
          .catch(function () {
            box.className = "brain-test-result err";
            box.textContent = "Không gọi được API kiểm tra.";
          })
          .then(function () { btn.disabled = false; });
      });
    });

    /* ---------- quay lại ---------- */
    document.querySelectorAll("[data-back]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (window.history.length > 1) window.history.back();
        else window.location.href = "/";
      });
    });
  });
})();
