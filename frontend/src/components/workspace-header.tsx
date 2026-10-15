"use client";
import Link from "next/link";

export function WorkspaceHeader() {
  const fixture = !process.env.NEXT_PUBLIC_API_BASE_URL;
  return <>
    <a className="skip-link" href="#workspace-content">Skip to workspace</a>
    <header className="workspace-header">
      <Link href="/" className="brand-lockup"><span className="brand-mark" aria-hidden="true">R</span><span>Ryde Tribunal<small>Evidence. Policy. Fair decisions.</small></span></Link>
      <nav aria-label="Workspace navigation"><Link href="/">Workspace</Link><Link href="/file-dispute">File a dispute</Link></nav>
      <span className="workspace-mode">{fixture ? "Recorded examples" : "Local reviewer workspace"}</span>
    </header>
    {fixture && <div className="mode-notice" role="status">Fixture mode · These are recorded synthetic examples. Provider names in examples do not demonstrate live AI calls. Filing and review changes are simulated.</div>}
  </>;
}
