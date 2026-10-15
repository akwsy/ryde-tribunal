import { CaseView } from "@/components/case-view";

/**
 * Case view route: /cases/[caseId]
 *
 * Case detail route.
 */
export default async function CasePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <CaseView caseId={caseId} />;
}
