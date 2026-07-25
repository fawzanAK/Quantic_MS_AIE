import { useState } from "react";
import { subscribeNewsletter } from "../api";
import "./Newsletter.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Newsletter({ compact = false }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState({ state: "idle", message: "" });

  async function handleSubmit(e) {
    e.preventDefault();

    if (!email.trim()) {
      setStatus({ state: "error", message: "Email is required." });
      return;
    }
    if (!EMAIL_RE.test(email.trim())) {
      setStatus({ state: "error", message: "Please enter a valid email address." });
      return;
    }

    setStatus({ state: "loading", message: "" });
    try {
      const result = await subscribeNewsletter(email.trim());
      if (result.success) {
        setStatus({ state: "success", message: result.message || "You're subscribed!" });
        setEmail("");
      } else {
        const message = result.errors?.email || result.message || "Something went wrong.";
        setStatus({ state: "error", message });
      }
    } catch (err) {
      setStatus({ state: "error", message: "Could not reach the server. Please try again." });
    }
  }

  return (
    <form className={`newsletter ${compact ? "newsletter--compact" : ""}`} onSubmit={handleSubmit} noValidate>
      <div className="newsletter__row">
        <input
          type="email"
          placeholder="you@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-label="Email address"
        />
        <button type="submit" className="btn-primary" disabled={status.state === "loading"}>
          {status.state === "loading" ? "..." : "Sign Up"}
        </button>
      </div>
      {status.state === "error" && <p className="newsletter__msg newsletter__msg--error">{status.message}</p>}
      {status.state === "success" && <p className="newsletter__msg newsletter__msg--success">{status.message}</p>}
      {status.state === "idle" && !compact && (
        <p className="newsletter__hint">* Required field; validated on submit for a well-formed email address.</p>
      )}
    </form>
  );
}
