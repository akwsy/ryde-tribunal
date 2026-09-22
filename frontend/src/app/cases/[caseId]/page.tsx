import { CaseView } from "@/components/case-view";

/**
 * Case view route: /cases/[caseId]
 *
 * Phase One will add /dashboard at the root, and this route stays as-is.
 */
export default async function CasePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <CaseView caseId={caseId} />;
}
