import type { ComponentPropsWithoutRef } from "react";
import type { LinksFunction, LoaderFunctionArgs } from "@remix-run/node";
import {
  Link as RemixLink,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  isRouteErrorResponse,
  useLoaderData,
  useNavigation,
  useRouteError,
} from "@remix-run/react";
import { AppProvider, Banner, BlockStack, Frame, Loading, Page, Text } from "@shopify/polaris";
import { messages } from "@/lib/messages";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import polarisStyles from "@shopify/polaris/build/esm/styles.css?url";

export const links: LinksFunction = () => [{ rel: "stylesheet", href: polarisStyles }];

const APP_BRIDGE_SRC = "https://cdn.shopify.com/shopifycloud/app-bridge.js";

interface RemixPolarisLinkProps extends ComponentPropsWithoutRef<"a"> {
  url: string;
  external?: boolean;
}

export async function loader(_args: LoaderFunctionArgs) {
  return {
    shopifyApiKey: process.env.SHOPIFY_API_KEY ?? "",
  };
}

function RemixPolarisLink({
  children,
  external,
  rel,
  target,
  url,
  ...rest
}: RemixPolarisLinkProps) {
  if (external) {
    return (
      <a
        href={url}
        rel={rel ?? "noopener noreferrer"}
        target={target ?? "_blank"}
        {...rest}
      >
        {children}
      </a>
    );
  }

  return (
    <RemixLink prefetch="intent" target={target} to={url} {...rest}>
      {children}
    </RemixLink>
  );
}

export default function App() {
  const { shopifyApiKey } = useLoaderData<typeof loader>();
  const navigation = useNavigation();
  const isNavigating = navigation.state !== "idle";

  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <meta name="shopify-api-key" content={shopifyApiKey} />
        <Meta />
        <Links />
        <script defer src={APP_BRIDGE_SRC} />
      </head>
      <body>
        <AppProvider i18n={polarisTranslations} linkComponent={RemixPolarisLink}>
          <Frame>
            {isNavigating && <Loading />}
            <Outlet />
          </Frame>
        </AppProvider>
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export function ErrorBoundary() {
  const error = useRouteError();

  let title: string = messages.errors.somethingWentWrong;
  let message: string = messages.errors.unexpectedError;

  if (isRouteErrorResponse(error)) {
    title = `${error.status} — ${error.statusText}`;
    message =
      error.status === 404
        ? messages.errors.pageNotFound
        : (typeof error.data === "string" ? error.data : message);
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body>
        <AppProvider i18n={polarisTranslations} linkComponent={RemixPolarisLink}>
          <Frame>
            <Page title={title}>
              <BlockStack gap="400">
                <Banner tone="critical">
                  <Text as="p" variant="bodyMd">{message}</Text>
                </Banner>
              </BlockStack>
            </Page>
          </Frame>
        </AppProvider>
        <Scripts />
      </body>
    </html>
  );
}
