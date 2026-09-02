# Frontend Architecture Guide

**(Next.js App Router · TanStack Query · REST API · Zod · React Context)**

> This document defines **how frontend code MUST be written**. Follow it exactly.
> It is a permanent reference — for human developers and AI coding assistants alike.

---

## 1. Core Principles (NON-NEGOTIABLE)

### 1.1 Architecture Flow

```
UI  →  Hooks  →  Services  →  API Client  →  REST API
```

- **UI never calls APIs or services directly**
- **Hooks never render UI**
- **Services are plain async functions — no hooks, no state**
- **API responses are always validated with Zod at the service layer**

### 1.2 State Ownership

| State type | Tool | Example |
|---|---|---|
| Server data (from API) | TanStack Query | Articles, authors, tags |
| Auth session | React Context (`AuthProvider`) | Logged-in user, token, role |
| Global UI state | Redux Toolkit slice | Sidebar open, active modal |
| Local component state | `useState` | Input value, dropdown open |
| Form state + errors | `useState` in hook | Form fields, validation errors |

**Never put API data in Redux. Never use TanStack Query for UI-only state.**

---

## 2. Folder Structure

```
src/
├── app/                                  # Next.js App Router — routes only
│   ├── layout.tsx                        # Root layout
│   ├── page.tsx                          # Home page
│   ├── provider.tsx                      # QueryClientProvider + AuthProvider
│   ├── robots.ts
│   ├── sitemap.ts
│   │
│   ├── (public)/                         # Public pages
│   │   ├── articles/[id]/page.tsx
│   │   ├── category/[category]/page.tsx
│   │   ├── region/[region]/page.tsx
│   │   └── tags/[tag]/page.tsx
│   │
│   ├── admin/
│   │   ├── layout.tsx
│   │   ├── page.tsx                      # Admin dashboard
│   │   ├── components/
│   │   │   └── DashboardLayout.tsx       # Admin layout shell
│   │   └── articles/
│   │       ├── page.tsx
│   │       ├── create/page.tsx
│   │       └── [id]/page.tsx
│   │
│   └── author/
│       ├── layout.tsx
│       ├── page.tsx
│       ├── components/
│       │   └── DashboardLayout.tsx
│       └── articles/
│           ├── page.tsx
│           ├── create/page.tsx
│           └── [id]/page.tsx
│
├── components/                           # Shared UI (not feature-specific)
│   ├── ui/                               # Atoms — Shadcn/Radix primitives
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   ├── dialog.tsx
│   │   ├── select.tsx
│   │   ├── checkbox.tsx
│   │   └── ...
│   │
│   └── molecules/                        # Shared molecules — used across features
│       ├── header.tsx
│       ├── footer.tsx
│       ├── loading.tsx
│       ├── category-badge.tsx
│       ├── region-badge.tsx
│       ├── status-badge.tsx
│       ├── image-picker.tsx
│       ├── pagination-controls.tsx
│       └── section-header.tsx
│
├── features/                             # Feature modules — own everything
│   │
│   ├── article/
│   │   ├── component/                    # Feature UI components
│   │   │   ├── article-card/
│   │   │   │   ├── article-card.tsx
│   │   │   │   └── article-card-vertical.tsx
│   │   │   ├── article-detail/
│   │   │   │   ├── header.tsx
│   │   │   │   ├── content.tsx
│   │   │   │   └── author.tsx
│   │   │   ├── article-form.tsx
│   │   │   ├── articles-table.tsx
│   │   │   └── articles-table-authorview.tsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── index.ts                  # Core API hooks (useQuery/useMutation) — shared
│   │   │   ├── useCreateArticleForm.ts   # Form hook for admin create page only
│   │   │   ├── useCreateArticleFormAuthor.ts  # Form hook for author create page only
│   │   │   └── useUpdateArticle.ts       # Form hook for edit page only
│   │   │
│   │   ├── services/
│   │   │   └── index.ts                  # All article service functions
│   │   │
│   │   └── types.ts                      # Article-specific Zod schemas + types
│   │
│   └── auth/
│       ├── hooks/
│       │   └── useAuth.tsx               # AuthContext + AuthProvider
│       ├── services/
│       │   ├── admin.ts
│       │   └── author.ts
│       └── types.ts                      # Auth-specific types
│
├── store/                                # Redux Toolkit (global UI state only)
│   ├── index.ts
│   ├── hooks.ts
│   └── slices/
│       └── uiSlice.ts
│
├── lib/
│   ├── api.ts                            # apiClient — typed fetch wrapper
│   └── utils.ts                          # cn(), formatDate(), etc.
│
├── hooks/                                # Global hooks (rare)
│   └── use-mobile.ts
│
└── types/                                # Shared types used by 2+ features
    ├── common.ts                         # ImageFile, Paginated<T>, Status, Category, Region, enums
    ├── auth.ts                           # UserRole, LoginCredentials
    └── constant.ts                       # API_BASE_URL and app-wide constants
```

---

## 3. Atomic Design Rules

### 3.1 Atoms — `components/ui/`

Pure UI primitives, no domain meaning. These are Shadcn/Radix components.

```tsx
// ✅ Atom — a button. Has no business meaning.
<Button variant="outline" onClick={handleCancel}>Cancel</Button>
```

Rules:
- No hooks
- No domain meaning (`Button`, not `ArticleSubmitButton`)
- Reusable anywhere in the project

---

### 3.2 Molecules — `components/molecules/` and `features/*/component/`

One meaningful domain thing, composed of atoms. No data fetching.

```tsx
// ✅ Molecule — one article card, receives article as prop
export function ArticleCard({ article, showRegionBadge = true }: ArticleCardProps) {
  return (
    <Link href={`/articles/${article.id}`} prefetch={false}>
      <div className="relative w-full aspect-3/2 overflow-hidden rounded-lg mb-3">
        <Image src={article.image.previewUrl} alt={article.title} fill className="object-cover" />
        <div className="absolute top-2 left-2 z-20">
          {showRegionBadge && <RegionBadge region={article.region} />}
        </div>
      </div>
      <h3 className="font-medium text-lg leading-tight line-clamp-2">{article.title}</h3>
    </Link>
  )
}
```

Rules:
- No custom hooks
- No API calls
- Accepts props, uses atoms
- Can have conditional UI logic and `useState` for local UI only

> **No custom hook needed → Molecule**

---

### 3.3 Organisms — feature components that use a hook

A component that needs a custom hook — data, async state, business logic.

```tsx
// ✅ Organism — uses useArticles hook, manages loading/empty states
export function ArticleList() {
  const { articles, isLoading } = useArticles()

  if (isLoading) return <LoadingArticleCard />
  if (!articles?.length) return <p>No articles found.</p>

  return (
    <div className="grid grid-cols-3 gap-6">
      {articles.map((a) => <ArticleCard key={a.id} article={a} />)}
    </div>
  )
}
```

Rules:
- Uses custom hooks for data or logic
- Can loop, manage loading/empty/error states
- Never calls API directly

> **Needs a custom hook → Organism**

---

### 3.4 Pages — `app/**/page.tsx`

Pages compose organisms, pass route params, never contain reusable UI.

```tsx
// ✅ Page — composes, never builds UI
export default function ArticlesPage() {
  return (
    <DashboardLayout>
      <ArticlesTable />
    </DashboardLayout>
  )
}
```

---

## 4. API Client — `lib/api.ts`

The single typed HTTP client for the entire app. All API calls go through here.

```ts
import imageCompression from 'browser-image-compression';
import { UploadImageResponse } from '@/types/common';
import { API_BASE_URL } from '@/types/constant';

// Custom error class — carries HTTP status code
export class RequestError extends Error {
  code: number;
  statusCode: number;

  constructor(message: string, code: number, statusCode: number) {
    super(message);
    this.name = 'RequestError';
    this.code = code;
    this.statusCode = statusCode;
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, RequestError);
    }
  }
}

// Every API response is wrapped in this shape
type ApiResponse<T> = {
  data: T;
  message: string;
  code: number;
  pagination?: {
    hasNext: boolean;
    nextCursor: number;
  };
};

export const apiClient = {
  async request<T>(endpoint: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
    try {
      const url = `${API_BASE_URL}${endpoint}`;
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...(token && { Authorization: `Bearer ${token}` }),
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new RequestError(
          errorData.message || 'Request failed',
          errorData.code || 0,
          response.status
        );
      }

      return response.json() as Promise<ApiResponse<T>>;
    } catch (error: any) {
      throw new RequestError(error.message || 'Request failed', 0, 500);
    }
  },

  get<T>(endpoint: string) { return this.request<T>(endpoint); },
  post<T>(endpoint: string, data: unknown) {
    return this.request<T>(endpoint, { method: 'POST', body: JSON.stringify(data) });
  },
  put<T>(endpoint: string, data: unknown) {
    return this.request<T>(endpoint, { method: 'PUT', body: JSON.stringify(data) });
  },
  patch<T>(endpoint: string, data: unknown) {
    return this.request<T>(endpoint, { method: 'PATCH', body: JSON.stringify(data) });
  },
  delete<T>(endpoint: string) {
    return this.request<T>(endpoint, { method: 'DELETE' });
  },

  // Image upload with compression before sending
  async uploadImage(file: File): Promise<ApiResponse<UploadImageResponse>> {
    const compressed = await imageCompression(file, { maxSizeMB: 0.5, useWebWorker: true });
    const formData = new FormData();
    formData.append('image', compressed);

    const token = localStorage.getItem('auth_token');
    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: 'POST',
      headers: { ...(token && { Authorization: `Bearer ${token}` }) },
      body: formData,
    });

    if (!response.ok) throw new RequestError(`Upload failed: ${response.status}`, 0, response.status);
    return response.json();
  },
};
```

---

## 5. Types with Zod

### 5.1 Where Types Live

Feature-specific types live **with the feature**. Shared types live in `types/`.

```
Rule: feature-specific → features/*/types.ts
      used by 2+ features → types/common.ts (or types/auth.ts etc.)
```

| Type | Where | Why |
|---|---|---|
| `Article`, `ArticleUpdates` | `features/article/types.ts` | Only the article feature owns it |
| `Author`, `AuthorUpdates` | `features/author/types.ts` | Only the author feature owns it |
| `Status`, `Category`, `Region` | `types/common.ts` | Used across article, author, filter features |
| `ImageFile`, `Paginated<T>` | `types/common.ts` | Used everywhere |
| `UserRole`, `LoginCredentials` | `types/auth.ts` | Used by auth feature + route guards |

**Never import a type from one feature into another feature's folder:**

```ts
// ✅ Correct — article feature imports its own types
import { Article } from './types';           // same feature
import { Status, ImageFile } from '@/types/common'; // shared

// ❌ Wrong — author feature reaching into article feature
import { Article } from '@/features/article/types';
// If author needs Article, move Article to @/types/common
```

This keeps features fully self-contained. Deleting a feature deletes all its types too.

---

### 5.2 Zod Schemas — the only way to define API types

**All types are defined with Zod schemas. Never write plain interfaces for API data.**
Zod validates the API response at runtime — if the server changes shape, you catch it immediately.

```ts
// features/article/types.ts
import { z } from 'zod';
import { Category, Region, Status, ImageFile } from '@/types/common';

// Define the schema
export const ArticleSchema = z.object({
  id: z.number(),
  author_id: z.number(),
  title: z.string(),
  content: z.string(),
  category: z.enum(Category),
  region: z.enum(Region),
  status: z.enum(Status),
  image: z.string().transform((val): ImageFile => ({ previewUrl: val })),
  publish_date: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  rejection_reason: z.string().optional().nullable(),
});

// Infer the type from the schema — no duplication
export type Article = z.infer<typeof ArticleSchema>;

// Extend for views that include author info
export const ArticleViewWithAuthorSchema = ArticleSchema.extend({
  tags: z.array(z.string()),
  author_name: z.string(),
  author_email: z.string(),
  author_profile_photo_url: z.string().optional(),
});

export type ArticleViewWithAuthor = z.infer<typeof ArticleViewWithAuthorSchema>;

// Update payload type (plain, not a schema — it's input not output)
export type ArticleUpdates = {
  title?: string;
  content?: string;
  category?: string;
  region?: string;
  imageFile?: ImageFile;
  tags?: string[];
};
```

### 5.3 Shared primitives in `types/common.ts`

```ts
// types/common.ts
import { z, ZodTypeAny } from 'zod';

export enum Status {
  Draft = 'draft',
  Pending = 'pending',
  Approved = 'approved',
  Rejected = 'rejected',
}

export enum Category {
  Politics = 'politics',
  Environment = 'environment',
  Health = 'health',
  Tourism = 'tourism',
}

export type ImageFile = {
  previewUrl: string;
  file?: File;
};

// Cursor-based pagination wrapper
export type Paginated<T> = {
  data: T[];
  pagination: {
    hasNext: boolean;
    nextCursor: number;
  };
};

// Zod helper for paginated responses
export function withPagination<T extends ZodTypeAny>(schema: T) {
  return z.object({
    data: z.array(schema),
    pagination: z.object({
      hasNext: z.boolean(),
      nextCursor: z.number(),
    }),
  });
}
```

---

## 6. Services — `features/*/services/index.ts`

Services are **plain async functions**. They call `apiClient`, then **Zod-parse the response**.
No hooks. No state. No React.

```ts
// features/article/services/index.ts
import { apiClient } from '@/lib/api';
import { Article, ArticleSchema, ArticleViewWithAuthor, ArticleViewWithAuthorSchema } from '../types';
import { Status, withPagination, Paginated } from '@/types/common';

// Fetch all (admin)
export async function fetchAllArticles(cursor: number, limit: number): Promise<Article[]> {
  const result = await apiClient.get<Article[]>(`/articles/all?cursor=${cursor}&limit=${limit}`);
  return result.data.map((item) => ArticleSchema.parse(item));
}

// Fetch one (public)
export async function fetchArticleById(id: number): Promise<ArticleViewWithAuthor> {
  const result = await apiClient.get<ArticleViewWithAuthor>(`/articles/approved/${id}`);
  return ArticleViewWithAuthorSchema.parse(result.data);
}

// Fetch latest with cursor pagination
export async function fetchLatestArticles(cursor: number, limit: number): Promise<Paginated<Article>> {
  const result = await apiClient.get<Article[]>(`/articles/approved/latest?cursor=${cursor}&limit=${limit}`);
  return withPagination(ArticleSchema).parse(result);
}

// Create
export async function createArticle(
  title: string, content: string, authorId: number,
  tags: string[], status: string, category: string, region: string, image: string
): Promise<Article> {
  const result = await apiClient.post<Article>('/articles', {
    title, content, authorId, tags, status, category, region, image,
  });
  return ArticleSchema.parse(result.data);
}

// Update status (admin)
export async function updateArticleStatus(
  id: number, status: Status, rejectionReason?: string
): Promise<Article> {
  if (status === Status.Rejected && !rejectionReason) {
    throw new Error('Rejection reason is required');
  }
  const payload: Record<string, unknown> = { status };
  if (rejectionReason) payload.rejection_reason = rejectionReason;
  const result = await apiClient.patch<Article>(`/articles/${id}/status`, payload);
  return ArticleSchema.parse(result.data);
}

// Delete
export async function deleteArticle(id: number): Promise<Article> {
  const result = await apiClient.delete<Article>(`/articles/${id}`);
  return ArticleSchema.parse(result.data);
}
```

---

## 7. TanStack Query Hooks — `features/*/hooks/index.ts`

Hooks are the bridge between services and UI. They own all async state.

### 7.0 Hooks Folder Structure — Two Types of Hook Files

The hooks folder contains **two distinct types of files**:

```
features/article/hooks/
├── index.ts                      ← Core API hooks — useQuery/useMutation
├── useCreateArticleForm.ts       ← Form hook for create page only
├── useCreateArticleFormAuthor.ts ← Form hook for author create page only
├── useUpdateArticle.ts           ← Form hook for edit page only
└── useArticleFilterHook.ts       ← Filter/search UI hook for list page only
```

---

#### `index.ts` — Core API hooks (shared)

All `useQuery` and `useMutation` hooks that talk to the server live in `index.ts`. These are **shared** — any page, organism, or form hook in the feature imports from here.

`index.ts` is not a re-export barrel. The hook code is **written directly in it**. The name `index.ts` just means it is the main file of the folder — so imports resolve cleanly:

```ts
import { useArticles, useCreateArticle } from '@/features/article/hooks'
//                                                            ↑ resolves to hooks/index.ts
```

What belongs in `index.ts`:
- `useArticles` — fetch all articles
- `useCreateArticle` — mutation to create
- `useUpdateArticle` — mutation to update
- `useDeleteArticle` — mutation to delete
- `useArticleById` — fetch one article
- Any hook used by more than one place in the feature

---

#### Separate files — Page-specific form/logic hooks

When a page needs its own form state, validation, and handlers, that logic goes in a **dedicated file** inside the hooks folder — not in `index.ts`.

```ts
// features/article/hooks/useCreateArticleForm.ts
import { useCreateArticle } from '@/features/article/hooks' // ← imports from index.ts

export const useCreateArticleForm = () => {
  const [formData, setFormData] = useState<ArticleFormState>(initialForm)
  const [createArticle, isCreating] = useCreateArticle()

  const handleChange = (field: string, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  const validateForm = () => {
    if (!formData.title) { toast.error('Title is required'); return false }
    if (!formData.content) { toast.error('Content is required'); return false }
    return true
  }

  const handlePublish = async () => {
    if (!validateForm()) return
    await createArticle(formData.title, formData.content, ...)
    router.push('/admin/articles')
  }

  return { formData, handleChange, handlePublish, isCreating }
}
```

What belongs in a separate file:
- `useState` form state
- Validation logic
- `handleChange`, `handleSubmit`, `handleReset` handlers
- `useRouter` navigation after submit
- Toast messages
- Logic that is **only used by one page**

---

#### The rule

| Hook type | Where | Used by |
|---|---|---|
| `useQuery` / `useMutation` (API) | `hooks/index.ts` | Any component in the feature |
| Form state + validation + handlers | `hooks/useXxxForm.ts` | Only the one page it was made for |

**Form hooks always import their API hook from `index.ts` — never re-implement it:**

```ts
// ✅ Correct — form hook wraps the core API hook
import { useCreateArticle } from '@/features/article/hooks'

// ❌ Wrong — calling the service directly from a form hook
import { createArticle } from '@/features/article/services'
```

---

### 7.1 Provider Setup

```tsx
// app/provider.tsx
'use client';

import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { AuthProvider } from '@/features/auth/hooks/useAuth';

export default function Provider({ children }: { children: React.ReactNode }) {
  // useState ensures a new QueryClient per request in SSR — do NOT use a module-level constant
  const [queryClient] = useState(
    () => new QueryClient({
      defaultOptions: {
        queries: {
          gcTime: 1000 * 60 * 60,    // 1 hour in memory
          staleTime: 1000 * 60 * 10, // 10 minutes fresh
        },
      },
    })
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
```

---

### 7.2 Query Hooks

```ts
// features/article/hooks/index.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { apiClient } from '@/lib/api';
import {
  fetchAllArticles, fetchArticleById, createArticle,
  updateArticle, updateArticleStatus, deleteArticle,
} from '../services';
import { Article, ArticleUpdates } from '../types';
import { Status, ImageFile } from '@/types/common';

// Read query
export function useArticles() {
  const { data: articles, error, isLoading } = useQuery({
    queryKey: ['allArticle'],
    queryFn: () => fetchAllArticles(Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER),
  });
  return { articles, error, isLoading };
}

// Single article
export function useArticleById(id: number) {
  const { data: article, error, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => fetchArticleById(id),
    enabled: !!id,
  });
  return { article, error, isLoading };
}

// Stale time varies by data freshness need
export function useTrendingTags() {
  const { data, isLoading } = useQuery({
    queryKey: ['trendingTags'],
    queryFn: () => fetchTrendingTags(),
    staleTime: 6 * 60 * 60 * 1000, // 6 hours — tags change rarely
  });
  return { data, isLoading };
}
```

---

### 7.3 Mutation Hooks

**After a mutation succeeds, update the query cache directly with `setQueryData` — this avoids a round-trip refetch and keeps the UI instantly in sync.**

```ts
// Create — adds new item to cache list
export function useCreateArticle() {
  const queryClient = useQueryClient();

  const { mutateAsync } = useMutation({
    mutationFn: ({
      title, content, authorId, tags, status, category, region, imageUrl,
    }: {
      title: string; content: string; authorId: number; tags: string[];
      status: string; category: string; region: string; imageUrl: string;
    }) => createArticle(title, content, authorId, tags, status, category, region, imageUrl),

    onSuccess: (newArticle) => {
      // Prepend to the list — no refetch needed
      queryClient.setQueryData(['allArticle'], (old: Article[] = []) => [newArticle, ...old]);
    },
  });

  const articleCreate = useCallback(
    async (
      title: string, content: string, authorId: number, tags: string[],
      status: Status, category: string, region: string, image: ImageFile
    ) => {
      const uploadResponse = await apiClient.uploadImage(image.file!);
      const imageUrl = uploadResponse.data.url;
      await mutateAsync({ title, content, authorId, tags, status, category, region, imageUrl });
    },
    [mutateAsync]
  );

  return [articleCreate] as const;
}

// Update — patches the item in cache list
export function useUpdateArticle() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: ({ id, ...updates }: { id: number } & Omit<ArticleUpdates, 'imageFile'> & { imageUrl?: string }) =>
      updateArticle(id, updates.title, updates.content, updates.tags, updates.category, updates.region, updates.imageUrl),

    onSuccess: (updated) => {
      queryClient.setQueryData(['allArticle'], (old: Article[] = []) =>
        old.map((a) => (a.id === updated.id ? updated : a))
      );
    },
  });

  return { updateArticle: mutateAsync, isLoading: isPending };
}

// Status change — admin approve/reject
export function useUpdateArticleStatus() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: ({ id, status, rejectionReason }: { id: number; status: Status; rejectionReason?: string }) =>
      updateArticleStatus(id, status, rejectionReason),

    onSuccess: (updated) => {
      queryClient.setQueryData(['allArticle'], (old: Article[] = []) =>
        old.map((a) => (a.id === updated.id ? updated : a))
      );
    },
  });

  return { updateArticleStatus: mutateAsync, isLoading: isPending };
}

// Delete — removes from cache list
export function useDeleteArticle() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending, error } = useMutation({
    mutationFn: (id: number) => deleteArticle(id),
    onSuccess: (deleted) => {
      queryClient.setQueryData(['allArticle'], (old: Article[] = []) =>
        old.filter((a) => a.id !== deleted.id)
      );
    },
  });

  return { deleteArticle: mutateAsync, isLoading: isPending, error };
}
```

---

### 7.4 Hook Rules

- Always return `?? []` for arrays — **never return `undefined` arrays to UI**
- Always return `isLoading` and `error` alongside data
- Name mutations as verbs: `articleCreate`, `deleteArticle`, not `mutate`
- Set `staleTime` based on how often the data changes:
  - Breaking news: `0` (always fresh)
  - Latest articles: `10 * 60 * 1000` (10 min)
  - Tags, categories: `6 * 60 * 60 * 1000` (6 hours)

---

## 8. Auth — React Context

Auth is managed with **React Context**, not Redux. It handles login, logout, token storage, and refresh.

```tsx
// features/auth/hooks/useAuth.tsx
'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { UserRole, LoginCredentials } from '@/types/auth';
import { loginAdmin, refreshAdminToken } from '../services/admin';
import { loginAuthor, refreshAuthorToken } from '../services/author';

// User classes — extend base User with role-specific fields
class User {
  role: UserRole;
  token: string;
  refresh_token: string;
  constructor(role: UserRole, token = '', refresh_token = '') {
    this.role = role; this.token = token; this.refresh_token = refresh_token;
  }
}
class AdminUser extends User { id: number; email: string; /* ... */ }
class AuthorUser extends User { id: number; name: string; email: string; /* ... */ }
class UnknownUser extends User { constructor() { super(UserRole.UNKNOWN); } }

// Context
const AuthContext = createContext<AuthContextType>({
  user: new UnknownUser(),
  isLoading: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User>(new UnknownUser());
  const [isLoading, setIsLoading] = useState(true);

  function setLoginUser(user: User) {
    if (typeof window !== 'undefined') {
      localStorage.setItem('user', JSON.stringify(user));
      localStorage.setItem('auth_token', user.token);
    }
    setUser(user);
  }

  const login = async (credentials: LoginCredentials) => {
    if (credentials.userType === UserRole.ADMIN) {
      const result = await loginAdmin(credentials.email, credentials.password);
      setLoginUser(new AdminUser(result));
    } else {
      const result = await loginAuthor(credentials.email, credentials.password);
      setLoginUser(new AuthorUser(result));
    }
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    setUser(new UnknownUser());
  };

  useEffect(() => {
    // On mount: load user from localStorage, refresh token if expired
    const load = async () => {
      const token = localStorage.getItem('auth_token');
      const stored = localStorage.getItem('user');
      if (!token || !stored) { logout(); setIsLoading(false); return; }

      const parsed = JSON.parse(stored);
      if (isTokenExpired(token)) {
        await refreshToken(parsed).catch(logout);
      } else {
        setUser(parsed);
      }
      setIsLoading(false);
    };
    load();
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
export function isAuthorUser(user: User): user is AuthorUser { return user.role === UserRole.AUTHOR; }
export function isAdminUser(user: User): user is AdminUser { return user.role === UserRole.ADMIN; }
```

---

## 9. Redux Toolkit — Global UI State Only

Use Redux for UI state that must persist across navigations and be shared between distant components. **Never store API data here.**

```ts
// store/slices/uiSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface UiState {
  sidebarOpen: boolean;
  activeModal: string | null;
}

const uiSlice = createSlice({
  name: 'ui',
  initialState: { sidebarOpen: true, activeModal: null } as UiState,
  reducers: {
    toggleSidebar: (state) => { state.sidebarOpen = !state.sidebarOpen; },
    openModal: (state, action: PayloadAction<string>) => { state.activeModal = action.payload; },
    closeModal: (state) => { state.activeModal = null; },
  },
});

export const { toggleSidebar, openModal, closeModal } = uiSlice.actions;
export default uiSlice.reducer;
```

```ts
// store/hooks.ts
import { useDispatch, useSelector, TypedUseSelectorHook } from 'react-redux';
import type { RootState, AppDispatch } from './index';

// Always use these typed versions — never bare useDispatch/useSelector
export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
```

---

## 10. Styling Rules (STRICT)

> For the token pipeline, light/dark, namespaces, and what is or isn't allowed as an arbitrary value, see **§18 Design Tokens**. This section covers everything else.

### 10.1 Text Size Scale — No Arbitrary Sizes

Always use Tailwind's standard text scale. Arbitrary pixel sizes are **banned**.

| Instead of | Use | Approx size |
|---|---|---|
| `text-[9px]` | `text-xs` | 12px |
| `text-[11px]` | `text-xs` | 12px |
| `text-[13px]` | `text-sm` | 14px |
| `text-[14px]` | `text-sm` | 14px |
| `text-[15px]` | `text-base` | 16px |
| `text-[17px]` | `text-lg` | 18px |
| `text-[20px]` | `text-xl` | 20px |

```tsx
// ❌ Wrong
<span className="text-[11px] font-medium">Badge</span>

// ✅ Correct
<span className="text-xs font-medium">Badge</span>
```

---

### 10.2 Responsive Height — Use `vh`, Not `px`

```tsx
// ❌ Wrong — breaks on small screens
<section className="h-[82vh] min-h-[600px]">

// ✅ Correct — scales across all screen sizes
<section className="h-[82vh] min-h-[60vh]">
```

---

### 10.3 `cn()` for Conditional Classes

```ts
// lib/utils.ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

```tsx
// Usage — clean conditional class logic
<div className={cn(
  'rounded-md border px-3 py-2',
  isError && 'border-destructive',
  isDisabled && 'opacity-50 cursor-not-allowed',
)}>
```

---

## 11. Image Rules (`next/image`)

### 11.1 `fill` vs `width`/`height` — Pick ONE

**Use `fill`** when the image must fill a shaped container. Parent must be `relative` with explicit size.

```tsx
// ✅ fill — aspect-ratio container, image fills it
<div className="relative w-full aspect-3/2 overflow-hidden rounded-lg">
  <Image
    src={article.image.previewUrl || '/placeholder.svg'}
    alt={article.title}
    fill
    className="object-cover transition-all duration-500 group-hover:scale-105"
    sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
  />
</div>
```

**Use `width`/`height`** for fixed-size images (avatars, logos).

```tsx
// ✅ explicit size — no positioned parent needed
<Image
  src={author.profile_photo_url}
  alt={author.name}
  width={40}
  height={40}
  className="rounded-full object-cover"
/>
```

### 11.2 `sizes` Prop

Always set `sizes` when using `fill`. Omit when using explicit `width`/`height`.

```tsx
// Full-width hero
sizes="100vw"

// Card grid (3 cols on desktop)
sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
```

### 11.3 Fallback

For content with missing images, use a stable seeded placeholder:

```tsx
src={article.image.previewUrl || `/images/placeholder.png`}
// or stable picsum
src={article.image.previewUrl ?? `https://picsum.photos/seed/${article.id}/800/500`}
```

### 11.4 Remote Domains in `next.config.ts`

```ts
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'your-cdn.com' },
      { protocol: 'https', hostname: 'picsum.photos' },
    ],
  },
};
```

---

## 12. TypeScript Patterns

### 12.1 Zod-inferred Types Only for API Data

```ts
// ❌ Wrong — duplicating what Zod already defines
interface Article {
  id: number;
  title: string;
  // ...
}

// ✅ Correct — single source of truth
export const ArticleSchema = z.object({ id: z.number(), title: z.string() });
export type Article = z.infer<typeof ArticleSchema>;
```

### 12.2 Safe Array Access

```ts
// ❌ Wrong — TypeScript thinks this is always Article
const first = articles[0] as (typeof articles)[0] | undefined;

// ✅ Correct — returns Article | undefined natively
const first = articles.at(0);
```

### 12.3 Hook Return Contract — Always `?? []` for Arrays

```ts
// ✅ Every hook that returns an array must guarantee a safe default
const articles = data?.data ?? [];
const tags = tags ?? [];
return { articles, tags, isLoading, error };
```

Components check `isLoading` for skeleton display and always get a real array — they never need to null-check.

### 12.4 Typed Enums for API Contracts

```ts
// ✅ Enums enforced at both type-level and runtime (via Zod)
export enum Status {
  Draft = 'draft',
  Pending = 'pending',
  Approved = 'approved',
  Rejected = 'rejected',
}

// In Zod schema
status: z.enum(Status)   // runtime validation
```

### 12.5 Form Errors Generic Pattern

```ts
// Define per-form — only the fields that can have errors
export interface ArticleFormErrors {
  title?: string;
  content?: string;
  category?: string;
}

// In hook — collect ALL errors before setting state
const validate = (form: ArticleFormState): ArticleFormErrors => {
  const errs: ArticleFormErrors = {};
  if (!form.title.trim()) errs.title = 'Title is required';
  if (!form.category) errs.category = 'Category is required';
  return errs;
};
```

---

## 13. Form Handling

### 13.1 Form State Lives in Hooks, Not Components

```ts
// features/article/hooks/useCreateArticleForm.ts
export function useCreateArticleForm() {
  const [formData, setFormData] = useState(initialForm);
  const [errors, setErrors] = useState<ArticleFormErrors>({});
  const [articleCreate, isCreating] = useCreateArticle();

  const handleChange = useCallback((field: keyof ArticleFormState, value: unknown) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: undefined })); // clear error on change
  }, []);

  const handleSubmit = useCallback(async () => {
    const newErrors = validate(formData);
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    await articleCreate(/* ... */);
  }, [formData]);

  return { formData, errors, handleChange, handleSubmit, isCreating };
}
```

### 13.2 Required Field UI Pattern

```tsx
<div className="space-y-1.5">
  <Label htmlFor="title">
    Title <span className="text-destructive">*</span>
  </Label>
  <Input
    id="title"
    value={formData.title}
    onChange={(e) => onChange('title', e.target.value)}
    className={cn(errors?.title && 'border-destructive')}
  />
  {errors?.title && (
    <p className="text-sm text-destructive">{errors.title}</p>
  )}
</div>
```

---

## 14. Loading States

Use a consistent loading component across the app. Never write raw spinner JSX in organisms.

```tsx
// components/molecules/loading.tsx
export function LoadingArticleCard() {
  return (
    <div className="overflow-hidden rounded-lg bg-white">
      <div className="w-full aspect-video animate-pulse bg-gray-100 rounded-lg mb-3" />
      <div className="h-4 w-3/4 animate-pulse bg-gray-100 rounded mb-2" />
      <div className="h-3 w-1/4 animate-pulse bg-gray-100 rounded" />
    </div>
  );
}

export function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}
```

Pattern in organisms:

```tsx
export function ArticleList() {
  const { articles, isLoading } = useArticles();

  if (isLoading) return (
    <div className="grid grid-cols-3 gap-6">
      {Array.from({ length: 6 }).map((_, i) => <LoadingArticleCard key={i} />)}
    </div>
  );

  if (!articles?.length) return <EmptyState message="No articles found." />;

  return (
    <div className="grid grid-cols-3 gap-6">
      {articles.map((a) => <ArticleCard key={a.id} article={a} />)}
    </div>
  );
}
```

---

## 15. Decision Cheatsheet

| Question | Answer |
|---|---|
| One domain item UI, no hooks? | Molecule |
| Needs a custom hook? | Organism |
| Pure UI primitive (Button, Input)? | Atom (`components/ui/`) |
| Fetches or mutates data? | Hook + Service |
| Route layout/page? | Page (`app/`) |
| Server data (API response)? | TanStack Query |
| Auth session, logged-in user? | React Context (`useAuth`) |
| Sidebar open, active modal? | Redux |
| Local component toggle/value? | `useState` |
| Types for API data? | Zod schema + `z.infer<>` |
| Image fills a container? | `fill` + aspect-ratio parent |
| Image fixed size (avatar)? | explicit `width`/`height` |

---

## 16. What NOT to Do

**Architecture**
- API calls or service functions directly in components
- Hooks that return JSX
- Business logic duplicated across admin/author — use role checks
- Storing API data in Redux

**Types**
- Importing a type from one feature into another (`@/features/article/types` in author feature) — if two features need the same type, move it to `@/types/common`
- Writing a plain `interface` for API data — use Zod schema + `z.infer<>`
- `array[0] as T | undefined` — use `array.at(0)`
- Returning `undefined` arrays from hooks — always `?? []`
- `any` — use `unknown` and narrow it

**Styling**
- `style={{ ... }}` inline styles
- Hardcoded color values (`text-[#333]`, `bg-[#f5f5f5]`)
- Arbitrary text sizes (`text-[13px]`) — use the Tailwind scale
- `min-h-[600px]` on full-section containers — use `min-h-[60vh]`
- Both `fill` AND explicit `width`/`height` on `next/image` — pick one

**TanStack Query**
- Calling services directly from components — always go through hooks
- Not Zod-parsing the response in services — catch shape mismatches early
- Using `invalidateQueries` when `setQueryData` is sufficient (causes extra network requests)

---

## 18. Design Tokens — `globals.css` + Tailwind v4 `@theme`

**Every visual value is a token. Tokens flow through one pipeline: CSS variable → `@theme` mapping → Tailwind utility. Components never see a hex, never a raw pixel size outside the scale.**

### 18.1 The pipeline

```
:root { --paper: #fafaf7; }              ← raw value (one place)
       │
       ▼
@theme inline { --color-paper: var(--paper); }    ← name it for Tailwind
       │
       ▼
<div className="bg-paper">                ← consume in components
```

Only **`globals.css`** contains hex literals. Component code never does.

### 18.2 Light / dark — one attribute, no media query

`html[data-theme="dark"]` is the toggle. It re-declares the same CSS variables with dark values; every Tailwind utility downstream flips automatically because they all resolve through `var(--…)`.

```css
:root              { --paper: #fafaf7; --ink: #0f0f0e; /* … */ }
[data-theme="dark"]{ --paper: #0f0f0e; --ink: #fafaf7; /* … */ }

@theme inline {
  --color-paper: var(--paper);   /* light or dark — Tailwind doesn't care */
  --color-ink:   var(--ink);
}
```

A FOUC-safe init script in `app/layout.tsx` reads `localStorage` before paint and sets `data-theme` so the page never flashes the wrong palette. Toggle via the `useTheme` hook (`useSyncExternalStore` watching the `data-theme` mutation).

### 18.3 The Helm token namespaces

| Namespace | Tokens | Use for |
|---|---|---|
| Surfaces | `paper`, `paper-2`, `paper-3`, `stone-1/2/3` | Page bg, wells, hairlines |
| Ink | `ink`, `ink-2/3/4` | Text on paper (primary → muted) |
| Dark surfaces | `night`, `night-2/3`, `on-night`, `on-night-2` | Hero blocks, footer, code panes |
| Signal | `signal`, `signal-hover`, `signal-press`, `signal-tint`, `signal-ink` | The one accent. **One per screen, max.** |
| Semantic | `success`, `warning`, `danger`, `info` (+ `-tint` variants) | Status only — never decorative |
| Borders | `border`, `border-2`, `border-3` | Hairlines and emphasized dividers |
| Radii | `rounded-btn` (10px), `rounded-card` (14px), `rounded-window` (20px) | Use these. Don't reach for `rounded-[12px]`. |
| Shadows | `shadow-card`, `shadow-card-2`, `shadow-card-3`, `shadow-pop` | Soft, warm, never blue. Plus `shadow-signal-glow`, `shadow-success-glow` for status dots. |
| Tracking | `tracking-display` (-0.04em), `tracking-h` (-0.03em), `tracking-caps` (0.08em) | Display headings, headlines, and uppercase eyebrows. |
| Type | `text-display-1/2/3` (clamp), `text-micro` (11px), `text-nano` (9px) | Hero / story headings, plus in-mock chrome (browser preview field labels). |

Brand colors from third-party mock screenshots (Stripe purple, etc.) live under `--color-brand-<name>` and are **only used inside the simulated job-board previews and the marketing logo marquee** — not for real Helm UI.

Composite page-edge effects (the hero radial backdrop, marquee edge fades) live as their own `--<name>` variables (e.g. `--hero-backdrop`, `--marquee-fade-left/right`) and are consumed by `@layer components` helper classes (`.hero-backdrop`, `.marquee-fades`) in `globals.css`. Components reach for the helper class, not the variable.

### 18.4 Adding a new token

1. Add the raw value in `:root` and (if it differs) in `[data-theme="dark"]`.
2. Map it under `@theme inline` so Tailwind generates a utility:
   - Color → `--color-<name>` → `bg-<name>`, `text-<name>`, `ring-<name>`
   - Radius → `--radius-<name>` → `rounded-<name>`
   - Shadow → `--shadow-<name>` → `shadow-<name>`
   - Tracking → `--tracking-<name>` → `tracking-<name>`
   - Text size → `--text-<name>` → `text-<name>`
3. Reference the design intent in a comment (which Helm system token it mirrors).

Never inline a hex in a component. Never reach for `text-[13px]`, `rounded-[14px]`, `bg-[#abc]`. If the token doesn't exist yet, add it in step 1 and 2 — don't bypass the pipeline.

### 18.5 What still allows arbitrary values

Layout-only and one-off transform/positioning hints that don't carry brand meaning:

- `w-[320px]`, `h-[calc(100%-60px)]` for one-off mock-window dimensions
- `rotate-[1.6deg]` for a single playful tilt
- `right-[-40px]` for a floating overlap

These are not visual design tokens; they're geometry. Adding them to `@theme` would pollute the namespace. Keep them inline.

### 18.6 Animations

Keyframes live in `globals.css` (`helm-pulse-dot`, `helm-blink`). Components reference them with `animate-[helm-pulse-dot_1.2s_var(--ease-in-out)_infinite]`. The easing curves (`--ease-out`, `--ease-in-out`, `--ease-emphatic`) and motion durations come from the Helm tokens and are re-exposed via `@theme`.

### 18.7 What NOT to do

- Hex color in a component — `text-[#ff5a1f]` instead of `text-signal`.
- Arbitrary radii / text sizes — `rounded-[14px]` instead of `rounded-card`, `text-[13px]` instead of `text-sm`.
- Inline `style={{ color: ... }}` — never.
- Tailwind `@theme` block in any file other than `globals.css`.
- A new "brand" or "accent" color outside the existing namespaces — if you reach for one, the design is wrong, not the token system.

```tsx
// ❌ Wrong — hardcoded values bypass the token pipeline
<p className="text-[#666] text-[13px]">Body text</p>

// ✅ Correct — utilities resolve through globals.css → @theme → Tailwind
<p className="text-ink-3 text-sm">Body text</p>
```

---

## 19. Final Rule

> **Feature types live with the feature — shared types live in `src/types/`**
> **Calls live in Services**
> **State lives in Hooks**
> **Server state lives in TanStack Query**
> **Auth lives in React Context**
> **UI state lives in Redux**
> **Tokens live in `globals.css` — see §18**
> **Meaning lives in Molecules**
> **Logic lives in Organisms**

Follow these rules and the codebase stays clean, scalable, and maintainable — in any project, at any team size.
