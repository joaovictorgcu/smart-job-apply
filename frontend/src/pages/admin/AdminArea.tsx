import { Route, Routes } from 'react-router-dom';

import { AdminShell } from '@/components/admin/AdminShell';
import { NotFound } from '@/pages/NotFound';

import { AdminDashboard } from './AdminDashboard';
import { AdminJobs } from './AdminJobs';
import { AdminLogs } from './AdminLogs';
import { AdminUsers } from './AdminUsers';

/**
 * Every /admin route, in one module that `App` loads lazily.
 *
 * The split is the point: this pulls in the shell, four pages and a dozen
 * panels, and almost nobody who signs in is an administrator. Declaring the
 * routes here (rather than in `App`) is what lets the whole area be one dynamic
 * import instead of five.
 *
 * Default-exported because `React.lazy` takes a module whose default is the
 * component.
 */
export default function AdminArea() {
  return (
    <Routes>
      <Route element={<AdminShell />}>
        <Route index element={<AdminDashboard />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="jobs" element={<AdminJobs />} />
        <Route path="logs" element={<AdminLogs />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
