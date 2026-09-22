import { redirect } from "next/navigation";

/**
 * Root page — redirects to a default case view in fixture mode.
 *
 * Phase One will replace this with the dashboard.
 */
export default function Home() {
  redirect("/cases/DSP-000045");
}
