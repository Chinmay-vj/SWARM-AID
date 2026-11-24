import { Link, useLocation } from "react-router-dom";
import { Panel } from "../../components/ui/primitives";
import { EmptyState } from "../../components/ui/states";

export default function NotFoundPage() {
  const location = useLocation();
  return (
    <Panel>
      <EmptyState title="Page not found">
        <p>
          No dashboard view exists at <code>{location.pathname}</code>.
        </p>
        <p>
          <Link to="/missions">Go to missions</Link>
        </p>
      </EmptyState>
    </Panel>
  );
}
