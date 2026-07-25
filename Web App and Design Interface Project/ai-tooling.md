# AI Tooling Summary

This project was developed with Claude (Anthropic) used across three stages: planning, wireframing, and implementation.

## 1. Planning
Claude was given the course's Software Requirements Specification PDF and used to break the assignment down into a build plan: project scaffolding, database schema, backend API endpoints, frontend pages, styling approach, and the presentation/submission checklist. This kept the SRS requirements (5 pages, reservation logic, newsletter signup, PostgreSQL schema) explicit and trackable throughout the build instead of being re-derived from memory partway through.

## 2. Wireframing
Low/mid-fidelity wireframes for all 5 pages (desktop + mobile variants, with layout/interaction annotations noting where Flexbox vs. Grid was intended) were generated using Claude's design tool, based on a detailed prompt describing Café Fausse's fine-dining brand, required page content, and responsive requirements. These wireframes were then used directly as the structural reference for the React components — for example, the header's Flexbox row, the footer's 4-column Grid, the menu's 2-column item Grid, and the gallery's masonry Grid all follow the wireframe's layout notes.

## 3. Implementation
Claude Code (via Cowork) was used to:
- Scaffold the Flask backend (SQLAlchemy models for `Customer`, `Reservation`, `NewsletterSignup`; blueprints for reservations and newsletter signup; the random-table-assignment and slot-availability logic).
- Scaffold the React frontend with Vite, React Router, and CSS matching each wireframe page.
- Write and run a local smoke test of the reservation logic (using SQLite as a stand-in for PostgreSQL, since the development sandbox had no local Postgres server) to confirm: successful bookings assign a table, a fully-booked slot correctly returns an error, and email validation rejects malformed addresses on both the reservation and newsletter endpoints.
- Push the resulting project directly to the GitHub repository via a scoped personal access token provided for this purpose.

## What worked well
- Generating wireframes first and treating them as the layout spec made the CSS decisions (Flexbox vs. Grid, breakpoints) unambiguous rather than something to improvise per component.
- Having the SRS requirements available meant the backend logic (30-table random assignment, required vs. optional fields) could be implemented directly from the spec without needing repeated clarification.

## What didn't / limitations
- The development sandbox does not have PostgreSQL installed, so the reservation and newsletter logic was verified end-to-end against SQLite locally as a substitute before running against a real PostgreSQL instance. The SQLAlchemy models are database-agnostic, so this doesn't affect the production configuration, but it means the author should re-verify against a real local PostgreSQL install before recording the demo.
- All photography in the Gallery/Home/About pages currently uses placeholder stock photo URLs; these should be swapped for the restaurant's own royalty-free or AI-generated images before the final demo, per the assignment's image requirement.
