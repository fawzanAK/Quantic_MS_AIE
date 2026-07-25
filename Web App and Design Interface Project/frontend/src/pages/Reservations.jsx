import { useEffect, useState } from "react";
import { createReservation } from "../api";
import "./Reservations.css";

const TIME_SLOTS = ["17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00"];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function formatSlotLabel(slot) {
  const [h, m] = slot.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${m.toString().padStart(2, "0")} ${period}`;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function Reservations() {
  const [form, setForm] = useState({
    date: todayIso(),
    guests: 2,
    time: TIME_SLOTS[3],
    name: "",
    email: "",
    phone: "",
    newsletter_signup: false,
  });
  const [fullSlots, setFullSlots] = useState([]);
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null); // { type: 'success' | 'error', ... }
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";
    fetch(`${apiBase}/api/reservations/availability?date=${form.date}`)
      .then((res) => res.json())
      .then((data) => setFullSlots(data.full_slots || []))
      .catch(() => setFullSlots([]));
  }, [form.date]);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function validate() {
    const nextErrors = {};
    if (!form.name.trim()) nextErrors.name = "Full name is required.";
    if (!form.email.trim()) nextErrors.email = "Email is required.";
    else if (!EMAIL_RE.test(form.email.trim())) nextErrors.email = "Please enter a valid email address.";
    if (!form.guests || form.guests < 1) nextErrors.guests = "Enter at least 1 guest.";
    if (!form.date || !form.time) nextErrors.time_slot = "Choose a date and time.";
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setResult(null);
    try {
      const response = await createReservation({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        guests: Number(form.guests),
        time_slot: `${form.date}T${form.time}`,
        newsletter_signup: form.newsletter_signup,
      });

      if (response.success) {
        setResult({
          type: "success",
          table: response.reservation.table_number,
          date: form.date,
          time: formatSlotLabel(form.time),
          guests: form.guests,
        });
      } else if (response.status === 409) {
        setResult({ type: "error", message: response.message });
      } else {
        setErrors(response.errors || {});
      }
    } catch (err) {
      setResult({ type: "error", message: "Could not reach the server. Please try again." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="reservations-page container">
      <h1>Reserve a Table</h1>

      {result?.type === "success" && (
        <div className="reservation-state reservation-state--success">
          <h2>✓ Reservation Confirmed</h2>
          <p>
            Table {result.table} · {result.date} · {result.time} · {result.guests} guests
            <br />
            A confirmation has been sent to your email.
          </p>
          <button className="btn-outline" onClick={() => setResult(null)}>
            Make another reservation
          </button>
        </div>
      )}

      {result?.type === "error" && (
        <div className="reservation-state reservation-state--error">
          <h2>⚠ That time is fully booked</h2>
          <p>{result.message}</p>
          <button className="btn-outline" onClick={() => setResult(null)}>
            Try another time
          </button>
        </div>
      )}

      {!result && (
        <form className="reservation-form" onSubmit={handleSubmit} noValidate>
          <div className="reservation-form__grid">
            <label>
              Date
              <input type="date" value={form.date} min={todayIso()} onChange={(e) => update("date", e.target.value)} />
            </label>
            <label>
              Guests
              <input
                type="number"
                min="1"
                max="20"
                value={form.guests}
                onChange={(e) => update("guests", e.target.value)}
              />
              {errors.guests && <span className="field-error">{errors.guests}</span>}
            </label>
          </div>

          <div className="reservation-form__field">
            <label>Time Slot</label>
            <div className="time-slot-grid">
              {TIME_SLOTS.map((slot) => {
                const isFull = fullSlots.includes(slot);
                return (
                  <button
                    type="button"
                    key={slot}
                    disabled={isFull}
                    className={`time-slot ${form.time === slot ? "time-slot--selected" : ""} ${isFull ? "time-slot--full" : ""}`}
                    onClick={() => update("time", slot)}
                  >
                    {formatSlotLabel(slot)}
                  </button>
                );
              })}
            </div>
            <p className="field-hint">Struck-through slot = fully booked, disabled</p>
          </div>

          <div className="reservation-form__grid">
            <label>
              Full Name
              <input type="text" value={form.name} onChange={(e) => update("name", e.target.value)} />
              {errors.name && <span className="field-error">{errors.name}</span>}
            </label>
            <label>
              Email *
              <input type="email" value={form.email} onChange={(e) => update("email", e.target.value)} />
              {errors.email && <span className="field-error">{errors.email}</span>}
            </label>
          </div>

          <label className="reservation-form__narrow">
            Phone (optional)
            <input type="tel" value={form.phone} onChange={(e) => update("phone", e.target.value)} />
          </label>

          <label className="reservation-form__checkbox">
            <input
              type="checkbox"
              checked={form.newsletter_signup}
              onChange={(e) => update("newsletter_signup", e.target.checked)}
            />
            Sign me up for the newsletter too
          </label>

          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "Submitting…" : "Request Reservation"}
          </button>
          <p className="field-hint">* Email required &amp; format-validated; name and date/time/guests required; phone optional.</p>
        </form>
      )}
    </div>
  );
}
