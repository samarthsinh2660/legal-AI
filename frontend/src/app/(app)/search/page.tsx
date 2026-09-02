import { SearchScreen } from "@/features/search/component/search-screen";

/** Screen 6 in design/UX_FLOWS.md. `searchParams` is a Promise in Next 16. */
export default async function SearchPage(props: PageProps<"/search">) {
  const { q } = await props.searchParams;
  return <SearchScreen initialQuery={typeof q === "string" ? q : undefined} />;
}
