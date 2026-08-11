import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AppShell } from "@/components/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AuthProvider } from "@/hooks/useAuth";
import { EventsProvider } from "@/hooks/useEvents";
import { ThemeProvider } from "@/lib/theme";
import { ApiError } from "@/services/client";
import { Activity } from "@/pages/Activity";
import { ApplicationDetail } from "@/pages/ApplicationDetail";
import { Applications } from "@/pages/Applications";
import { Dashboard } from "@/pages/Dashboard";
import { JobDetail } from "@/pages/JobDetail";
import { Jobs } from "@/pages/Jobs";
import { Login } from "@/pages/Login";
import { NotFound } from "@/pages/NotFound";
import { Profile } from "@/pages/Profile";
import { Register } from "@/pages/Register";
import { Searches } from "@/pages/Searches";
import { Settings } from "@/pages/Settings";

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // A rejected token or a missing resource will not fix itself.
          if (error instanceof ApiError) {
            if (error.status === 401 || error.status === 403 || error.status === 404) {
              return false;
            }
            if (error.status >= 400 && error.status < 500) return false;
          }
          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function App() {
  // Kept in state so React never recreates the cache on re-render.
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <EventsProvider>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />

                <Route
                  element={
                    <ProtectedRoute>
                      <AppShell />
                    </ProtectedRoute>
                  }
                >
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/jobs" element={<Jobs />} />
                  <Route path="/jobs/:id" element={<JobDetail />} />
                  <Route path="/applications" element={<Applications />} />
                  <Route path="/applications/:id" element={<ApplicationDetail />} />
                  <Route path="/searches" element={<Searches />} />
                  <Route path="/profile" element={<Profile />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/activity" element={<Activity />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </EventsProvider>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
