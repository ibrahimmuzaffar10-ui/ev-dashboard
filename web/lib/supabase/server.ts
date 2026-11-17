// Supabase client for Server Components / Server Actions: reads go through Row Level Security with the
// signed-in user's OWN session (anon key + their cookie). No service/admin key exists anywhere in web/.
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function supabaseServer() {
  const store = await cookies();
  return createServerClient(process.env.SUPABASE_URL!, process.env.SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (list) => {
        try {
          list.forEach(({ name, value, options }) => store.set(name, value, options));
        } catch {
          // called from a Server Component: the proxy refreshes the session cookies instead
        }
      },
    },
  });
}
