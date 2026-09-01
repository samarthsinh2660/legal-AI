"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import { AuthProvider } from "@/features/auth/hooks/useAuth";
import { RequestError } from "@/lib/api";

export default function Provider({ children }: { children: ReactNode }) {
  // In state, not a module constant: a module-level client is shared
  // between requests on the server, which would leak one user's data into
  // another's render.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            // Retrying a 401 or a 404 just delays the error the UI is
            // already able to show. Retry the ones that might be transient.
            retry: (failureCount, error) => {
              if (error instanceof RequestError && error.status < 500) {
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {children}
        <ReactQueryDevtools initialIsOpen={false} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
