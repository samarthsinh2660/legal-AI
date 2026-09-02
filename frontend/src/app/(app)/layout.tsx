import { AppSidebar } from "@/components/molecules/app-sidebar";
import { RequireAuth } from "@/features/auth/component/require-auth";

/** The authenticated shell. Login and register sit outside this group and
 *  so get none of it.
 *
 *  No top bar: the account moved into the sidebar, which is where the rest
 *  of the persistent chrome lives, and the header had nothing else in it. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <RequireAuth>
      <div className="flex min-h-screen flex-1">
        <AppSidebar />
        <main className="min-w-0 flex-1 overflow-y-auto p-6 lg:p-8">
          {children}
        </main>
      </div>
    </RequireAuth>
  );
}
