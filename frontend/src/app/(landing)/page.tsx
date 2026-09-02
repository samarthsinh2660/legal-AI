import { Landing } from "@/features/landing/component/landing";

/**
 * The public home page, at `/`.
 *
 * `(landing)` is a route group, so it names the folder without appearing
 * in the URL. It sits outside `(app)`, which wraps everything in
 * RequireAuth -- a visitor with no account has to be able to read this.
 * The dashboard lives at /dashboard.
 */
export default function HomePage() {
  return <Landing />;
}
