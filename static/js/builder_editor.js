/* 問卷編輯器 —— Vue 3（CDN、Options API、無建構工具）
 *
 * 三欄：大綱 / 題目卡 / 家長端即時預覽。所有變更即時打 builder API
 * （debounce），成功後刷新右側預覽 iframe。
 * 只有草稿版本可編輯；非草稿時所有輸入 disabled，僅提供「複製為新版本」。
 */
(function () {
  "use strict";

  const el = document.getElementById("app");
  const cfg = {
    versionId: el.dataset.versionId,
    csrf: el.dataset.csrf,
    previewUrl: el.dataset.previewUrl,
    listUrl: el.dataset.listUrl,
  };

  async function api(url, method = "GET", body) {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = "HTTP " + res.status;
      try { detail = (await res.json()).detail || JSON.stringify(await res.json()); } catch {}
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  const STATUS_LABEL = { draft: "草稿", published: "已發布", retired: "已停用" };

  Vue.createApp({
    compilerOptions: { delimiters: ["{[", "]}"] },

    data() {
      return {
        tree: {},
        selected: null,           // 目前編輯的題目
        selectedSection: null,    // 目前編輯的題組（未選題目時）
        ruleTarget: {},           // {ruleId: "section:3" | "question:5"}
        saveHint: "",
        previewNonce: 0,
      };
    },

    computed: {
      statusLabel() { return STATUS_LABEL[this.tree.status] || this.tree.status; },

      previewSrc() {
        return cfg.previewUrl + "&_n=" + this.previewNonce;
      },

      allQuestions() {
        const out = [];
        (this.tree.sections || []).forEach((s) => s.questions.forEach((q) => out.push(q)));
        return out;
      },

      rulesForSelected() {
        if (!this.selected) return [];
        return (this.tree.branch_rules || []).filter((r) => r.trigger_question === this.selected.id);
      },

      canPublish() {
        return this.tree.is_editable && this.allQuestions.length > 0;
      },
    },

    async mounted() {
      await this.load();
    },

    methods: {
      async load() {
        this.tree = await api(`/api/builder/versions/${cfg.versionId}/`);
        (this.tree.eligibility_rules || []).forEach((rule) => {
          if (!rule.condition_json) rule.condition_json = {};
          rule.condition_json = Object.assign({
            period: "any", frequency: "any", timing: "any", start_date: "", end_date: "",
          }, rule.condition_json);
        });
        // config 可能是 null，補成物件方便 v-model
        this.tree.sections.forEach((s) =>
          s.questions.forEach((q) => { if (!q.config) q.config = {}; })
        );
        // 初始化 ruleTarget
        (this.tree.branch_rules || []).forEach((r) => {
          if (r.target_section) this.ruleTarget[r.id] = "section:" + r.target_section;
          else if (r.target_question) this.ruleTarget[r.id] = "question:" + r.target_question;
          else if (r.target_questionnaire) this.ruleTarget[r.id] = "questionnaire:" + r.target_questionnaire;
        });
      },

      flash(msg) {
        this.saveHint = msg;
        clearTimeout(this._hintT);
        this._hintT = setTimeout(() => { this.saveHint = ""; }, 2500);
      },

      async refreshPreview() {
        this.previewNonce++;
      },

      afterSave() {
        this.flash("已儲存");
        this.refreshPreview();
      },

      handleErr(e) {
        if (e.status === 409) {
          alert(e.message);
          this.load();
        } else {
          this.flash("儲存失敗：" + e.message);
        }
      },

      // --- 選取 ---
      selectQuestion(q, sec) {
        this.selected = q;
        this.selectedSection = sec;
      },
      selectSection(sec) {
        this.selectedSection = sec;
        this.selected = null;
      },

      // --- 題組 ---
      async addSection() {
        try {
          const sec = await api(`/api/builder/versions/${cfg.versionId}/sections/`, "POST",
            { title: "新題組" });
          sec.questions = sec.questions || [];
          this.tree.sections.push(sec);
          this.selectSection(sec);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      saveSectionDebounced: null,  // 於 created 綁
      async saveSection() {
        const s = this.selectedSection;
        try {
          await api(`/api/builder/sections/${s.id}/`, "PATCH",
            { title: s.title, description: s.description });
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async deleteSection(sec) {
        if (!confirm(`刪除題組「${sec.title}」及其下所有題目？`)) return;
        try {
          await api(`/api/builder/sections/${sec.id}/`, "DELETE");
          this.tree.sections = this.tree.sections.filter((s) => s.id !== sec.id);
          this.selected = null; this.selectedSection = null;
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async moveSection(index, dir) {
        const arr = this.tree.sections;
        const j = index + dir;
        if (j < 0 || j >= arr.length) return;
        [arr[index], arr[j]] = [arr[j], arr[index]];
        await this.persistOrder();
      },

      // --- 題目 ---
      async addQuestion(sec) {
        try {
          const q = await api(`/api/builder/sections/${sec.id}/questions/`, "POST",
            { prompt: "新題目", question_type: "single" });
          q.config = q.config || {};
          q.options = q.options || [];
          sec.questions.push(q);
          this.selectQuestion(q, sec);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      saveQuestionDebounced: null,
      async saveQuestion() {
        const q = this.selected;
        try {
          await api(`/api/builder/questions/${q.id}/`, "PATCH", {
            prompt: q.prompt, help_text: q.help_text, question_type: q.question_type,
            required: q.required, config: q.config || {},
          });
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async deleteQuestion(q) {
        if (!confirm("刪除這一題？")) return;
        try {
          await api(`/api/builder/questions/${q.id}/`, "DELETE");
          this.selectedSection.questions = this.selectedSection.questions.filter((x) => x.id !== q.id);
          this.selected = null;
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async moveQuestion(sec, index, dir) {
        const j = index + dir;
        if (j < 0 || j >= sec.questions.length) return;
        [sec.questions[index], sec.questions[j]] = [sec.questions[j], sec.questions[index]];
        await this.persistOrder();
      },

      async persistOrder() {
        const payload = {
          sections: this.tree.sections.map((s) => s.id),
          questions: {},
        };
        this.tree.sections.forEach((s) => {
          payload.questions[s.id] = s.questions.map((q) => q.id);
        });
        try {
          await api(`/api/builder/versions/${cfg.versionId}/reorder/`, "POST", payload);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },

      // --- 選項 ---
      async addOption() {
        try {
          const opt = await api(`/api/builder/questions/${this.selected.id}/options/`, "POST",
            { label: "新選項" });
          this.selected.options.push(opt);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      saveOptionDebounced(opt) { this._saveOptDeb(opt); },
      async saveOption(opt) {
        try {
          await api(`/api/builder/options/${opt.id}/`, "PATCH", { label: opt.label });
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async deleteOption(opt) {
        try {
          await api(`/api/builder/options/${opt.id}/`, "DELETE");
          this.selected.options = this.selected.options.filter((o) => o.id !== opt.id);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },

      // --- 跳題規則 ---
      async addRule() {
        const firstSection = this.tree.sections[0];
        try {
          const rule = await api(`/api/builder/versions/${cfg.versionId}/branch-rules/`, "POST", {
            trigger_question: this.selected.id,
            trigger_operator: "eq",
            trigger_value: this.selected.options[0] ? this.selected.options[0].value : "",
            action: "show",
            target_section: firstSection.id,
          });
          this.tree.branch_rules.push(rule);
          this.ruleTarget[rule.id] = "section:" + firstSection.id;
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      saveRuleDebounced(rule) { this._saveRuleDeb(rule); },
      async saveRule(rule) {
        try {
          const body = {
            trigger_operator: rule.trigger_operator,
            trigger_value: rule.trigger_operator === "answered" ? "" : rule.trigger_value,
            action: rule.action,
          };
          const updated = await api(`/api/builder/branch-rules/${rule.id}/`, "PATCH", body);
          rule.description = updated.description;
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async setRuleTarget(rule) {
        const [kind, id] = this.ruleTarget[rule.id].split(":");
        const body = { target_section: null, target_question: null, target_questionnaire: null };
        body[kind === "section" ? "target_section" :
          kind === "questionnaire" ? "target_questionnaire" : "target_question"] = Number(id);
        try {
          const updated = await api(`/api/builder/branch-rules/${rule.id}/`, "PATCH", body);
          Object.assign(rule, updated);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async deleteRule(rule) {
        try {
          await api(`/api/builder/branch-rules/${rule.id}/`, "DELETE");
          this.tree.branch_rules = this.tree.branch_rules.filter((r) => r.id !== rule.id);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },

      // --- 適用與排程規則 ---
      async addEligibilityRule() {
        try {
          const rule = await api(`/api/builder/versions/${cfg.versionId}/eligibility/`, "POST", {
            condition_json: { period: "any", frequency: "any", timing: "any", start_date: "", end_date: "" },
          });
          rule.condition_json = Object.assign({
            period: "any", frequency: "any", timing: "any", start_date: "", end_date: "",
          }, rule.condition_json || {});
          this.tree.eligibility_rules.push(rule);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      saveEligibilityDebounced(rule) { this._saveEligibilityDeb(rule); },
      async saveEligibility(rule) {
        try {
          await api(`/api/builder/eligibility/${rule.id}/`, "PATCH", {
            min_age_months: rule.min_age_months === "" ? null : rule.min_age_months,
            max_age_months: rule.max_age_months === "" ? null : rule.max_age_months,
            tracking_status: rule.tracking_status,
            condition_json: rule.condition_json,
          });
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },
      async deleteEligibilityRule(rule) {
        try {
          await api(`/api/builder/eligibility/${rule.id}/`, "DELETE");
          this.tree.eligibility_rules = this.tree.eligibility_rules.filter((item) => item.id !== rule.id);
          this.afterSave();
        } catch (e) { this.handleErr(e); }
      },

      // --- 發布 / 複製 ---
      async publish() {
        if (!confirm("發布這個版本？發布後內容將鎖定，家長既有的填答紀錄不受影響。")) return;
        try {
          this.tree = await api(`/api/builder/versions/${cfg.versionId}/publish/`, "POST");
          this.load();
          this.flash("已發布");
        } catch (e) { this.flash("發布失敗：" + e.message); }
      },
      async cloneVersion() {
        try {
          const v = await api(`/api/builder/versions/${cfg.versionId}/clone/`, "POST");
          location.href = `/build/version/${v.id}/`;
        } catch (e) { alert("複製失敗：" + e.message); }
      },
    },

    created() {
      this.saveSectionDebounced = debounce(this.saveSection, 700);
      this.saveQuestionDebounced = debounce(this.saveQuestion, 700);
      this._saveOptDeb = debounce(this.saveOption, 700);
      this._saveRuleDeb = debounce(this.saveRule, 700);
      this._saveEligibilityDeb = debounce(this.saveEligibility, 700);
    },
  }).mount("#app");
})();
