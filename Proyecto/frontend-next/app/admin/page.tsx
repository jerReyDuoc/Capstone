/** HU-27 · /admin → /admin/clientes */
import { redirect } from "next/navigation";

export default function Admin() {
  redirect("/admin/clientes");
}
