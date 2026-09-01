import { CaseWorkspace } from "@/features/case/component/case-workspace";

/** Screen 5b in design/UX_FLOWS.md. `params` is a Promise in Next 16. */
export default async function CasePage(props: PageProps<"/cases/[caseId]">) {
  const { caseId } = await props.params;
  return <CaseWorkspace caseId={caseId} />;
}
