// Minimal Stripe Elements flow.
//   1. GET  /api/config         -> publishable key
//   2. POST /api/payments/intent -> { clientSecret, … }
//   3. mount the PaymentElement bound to that clientSecret
//   4. on submit, stripe.confirmPayment({ elements, ... })
//   5. refresh the payments table

const $ = (s) => document.querySelector(s);

let stripe, elements, publishableKey, currency = "usd";
let currentClientSecret = null;

async function init() {
  const cfg = await fetch("/api/config").then(r => r.json());
  publishableKey = cfg.publishableKey;
  currency = cfg.currency || "usd";
  if (!publishableKey || !publishableKey.startsWith("pk_")) {
    $("#config-warning").hidden = false;
    $("#submit").disabled = true;
    return;
  }
  stripe = Stripe(publishableKey);
  await mountFreshElement();
  $("#submit").disabled = false;
  await refresh();
}

async function mountFreshElement() {
  // We need a fresh PaymentIntent (and clientSecret) for every attempt.
  const amount = readAmountCents();
  if (!amount) return;
  const description = $("#description").value || "Stripe POC";

  const res = await fetch("/api/payments/intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amountCents: amount, currency, description }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    setResult("err", "Failed to create PaymentIntent: " + err.message);
    return;
  }
  const { clientSecret } = await res.json();
  currentClientSecret = clientSecret;

  // Tear down any previous element.
  const mount = $("#payment-element");
  mount.replaceChildren();

  elements = stripe.elements({ clientSecret, appearance: { theme: "stripe" } });
  const paymentElement = elements.create("payment", { layout: "tabs" });
  paymentElement.mount(mount);
}

function readAmountCents() {
  const v = parseFloat($("#amount").value);
  if (!Number.isFinite(v) || v < 0.5) {
    setResult("err", "Amount must be at least 0.50");
    return null;
  }
  return Math.round(v * 100);
}

function setResult(cls, msg) {
  const el = $("#result");
  el.className = cls || "";
  el.textContent = msg || "";
}

$("#pay-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!stripe || !elements) return;
  setResult("", "Confirming…");
  $("#submit").disabled = true;

  const { error, paymentIntent } = await stripe.confirmPayment({
    elements,
    confirmParams: {
      return_url: window.location.origin + "/",
    },
    redirect: "if_required",
  });

  if (error) {
    setResult("err", error.message || "Payment failed");
  } else if (paymentIntent && paymentIntent.status === "succeeded") {
    setResult("ok", `Succeeded — ${paymentIntent.id}`);
  } else {
    setResult("", "Status: " + (paymentIntent ? paymentIntent.status : "unknown"));
  }

  // After any attempt we need a *new* PaymentIntent before allowing another submit.
  await refresh();
  await mountFreshElement();
  $("#submit").disabled = false;
});

// Re-create the PaymentIntent whenever the amount changes (so the Element
// reflects the new total). Cheap because we throttle to blur.
$("#amount").addEventListener("change", mountFreshElement);
$("#description").addEventListener("change", mountFreshElement);

$("#refresh").addEventListener("click", refresh);

async function refresh() {
  const rows = await fetch("/api/payments?limit=20").then(r => r.json()).catch(() => []);
  const tbody = $("#payments tbody");
  tbody.replaceChildren();
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${new Date(r.createdAt).toLocaleString()}</td>
      <td>${(r.amountCents / 100).toFixed(2)}</td>
      <td>${r.currency.toUpperCase()}</td>
      <td>${r.status}</td>
      <td><code>${r.stripeIntentId}</code></td>`;
    tbody.appendChild(tr);
  }
}

init().catch((e) => {
  console.error(e);
  setResult("err", "Init failed: " + e.message);
});
