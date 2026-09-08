import { CaseWorkspace } from "@/features/case/component/case-workspace";

/** One case's workspace. `params` is a Promise in Next 16. */
export default async function CasePage(props: PageProps<"/cases/[caseId]">) {
  const { caseId } = await props.params;
  return <CaseWorkspace caseId={caseId} />;
}
