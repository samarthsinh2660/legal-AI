import { Skeleton } from "@/components/ui/skeleton";

/** One placeholder row, shaped like the thread row it stands in for, so
 *  the layout does not jump when the data lands. */
export function LoadingRow() {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/4" />
      </div>
      <Skeleton className="h-3 w-16" />
    </div>
  );
}

export function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center">
      <div className="size-8 animate-spin rounded-full border-2 border-line border-b-primary" />
    </div>
  );
}
