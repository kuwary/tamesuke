/**
 * Tamesuke フロントエンド
 *
 * サブドメインのリアルタイムバリデーション + Checkout Session 作成
 */

const API_BASE = "";

// --- DOM 要素 ---
const form = document.getElementById("apply-form");
const submitBtn = document.getElementById("submit-btn");
const globalError = document.getElementById("form-global-error");

const subdomainInput = document.getElementById("subdomain");
const subdomainStatus = document.getElementById("subdomain-status");
const subdomainError = document.getElementById("subdomain-error");

// --- サブドメインバリデーション ---

let debounceTimer = null;
let lastCheckedSubdomain = "";
let subdomainAvailable = false;

/**
 * ローカルバリデーション（文字種・長さ・ハイフン位置）
 * @param {string} value
 * @returns {string|null} エラーメッセージ。問題なければ null
 */
function validateSubdomainLocal(value) {
  if (!value) return null;
  if (value.length > 12) {
    return "12文字以内で入力してください";
  }
  if (!/^[a-z0-9-]+$/.test(value)) {
    return "英小文字・数字・ハイフンのみ使用できます";
  }
  if (value.startsWith("-") || value.endsWith("-")) {
    return "ハイフンで始まる・終わることはできません";
  }
  return null;
}

function setSubdomainStatus(text, className) {
  subdomainStatus.textContent = text;
  subdomainStatus.className = "form-status " + className;
}

function clearSubdomainStatus() {
  subdomainStatus.textContent = "";
  subdomainStatus.className = "form-status";
  subdomainAvailable = false;
  lastCheckedSubdomain = "";
}

async function checkSubdomainAPI(value) {
  setSubdomainStatus("確認中...", "is-checking");
  try {
    const res = await fetch(
      API_BASE + "/api/check-subdomain?subdomain=" + encodeURIComponent(value)
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setSubdomainStatus(data.detail || "確認に失敗しました", "is-taken");
      subdomainAvailable = false;
      return;
    }
    const data = await res.json();
    lastCheckedSubdomain = value;
    if (data.available) {
      setSubdomainStatus("利用できます", "is-available");
      subdomainAvailable = true;
    } else {
      setSubdomainStatus("このサブドメインは使用されています", "is-taken");
      subdomainAvailable = false;
    }
  } catch {
    setSubdomainStatus("通信エラーが発生しました", "is-taken");
    subdomainAvailable = false;
  }
}

subdomainInput.addEventListener("input", function () {
  // 大文字を小文字に変換
  this.value = this.value.toLowerCase();

  const value = this.value;
  clearSubdomainStatus();
  subdomainError.textContent = "";
  this.classList.remove("is-error");

  if (!value) return;

  const localErr = validateSubdomainLocal(value);
  if (localErr) {
    subdomainError.textContent = localErr;
    this.classList.add("is-error");
    return;
  }

  // debounce 付き API チェック
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(function () {
    checkSubdomainAPI(value);
  }, 300);
});

// --- フォーム送信 ---

/**
 * 全フィールドのバリデーション
 * @returns {boolean}
 */
function validateForm() {
  let valid = true;

  // メールアドレス
  const email = document.getElementById("email");
  const emailError = document.getElementById("email-error");
  emailError.textContent = "";
  email.classList.remove("is-error");
  if (!email.value || !email.validity.valid) {
    emailError.textContent = "有効なメールアドレスを入力してください";
    email.classList.add("is-error");
    valid = false;
  }

  // 会社名
  const companyName = document.getElementById("company_name");
  const companyError = document.getElementById("company_name-error");
  companyError.textContent = "";
  companyName.classList.remove("is-error");
  if (!companyName.value.trim()) {
    companyError.textContent = "会社名を入力してください";
    companyName.classList.add("is-error");
    valid = false;
  }

  // サブドメイン
  const subdomain = subdomainInput.value;
  subdomainError.textContent = "";
  subdomainInput.classList.remove("is-error");
  if (!subdomain) {
    subdomainError.textContent = "サブドメインを入力してください";
    subdomainInput.classList.add("is-error");
    valid = false;
  } else {
    const localErr = validateSubdomainLocal(subdomain);
    if (localErr) {
      subdomainError.textContent = localErr;
      subdomainInput.classList.add("is-error");
      valid = false;
    } else if (!subdomainAvailable || lastCheckedSubdomain !== subdomain) {
      subdomainError.textContent =
        "サブドメインの利用可否を確認してください";
      subdomainInput.classList.add("is-error");
      valid = false;
    }
  }

  return valid;
}

form.addEventListener("submit", async function (e) {
  e.preventDefault();
  globalError.textContent = "";

  if (!validateForm()) return;

  // 送信中 UI
  submitBtn.disabled = true;
  submitBtn.textContent = "送信中...";

  const durationRadio = document.querySelector(
    'input[name="duration_days"]:checked'
  );

  const body = {
    email: document.getElementById("email").value,
    company_name: document.getElementById("company_name").value,
    oss_type: document.getElementById("oss_type").value,
    duration_days: Number(durationRadio.value),
    subdomain: subdomainInput.value,
  };

  try {
    const res = await fetch(API_BASE + "/api/create-checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "エラーが発生しました");
    }

    const data = await res.json();
    window.location.href = data.checkout_url;
  } catch (err) {
    globalError.textContent = err.message;
    submitBtn.disabled = false;
    submitBtn.textContent = "決済に進む";
  }
});
