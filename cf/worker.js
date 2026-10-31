import { Container, getContainer } from "@cloudflare/containers";

// Co-locates the FastAPI app (and its embedded MariaDB) in a single instance.
// defaultPort must match the port the container listens on (EXPOSE 5000).
export class LbvdContainer extends Container {
  defaultPort = 5000;
  sleepAfter = "15m";
}

export default {
  async fetch(request, env) {
    return getContainer(env.LBVD_CONTAINER).fetch(request);
  },
};
