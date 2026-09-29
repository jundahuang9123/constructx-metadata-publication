import { LoadedCatalog } from "../solid/catalogReader";

export interface PublishPayload {
  body: string;
  contentType: string;
  sourceLabel: string;
}

export function buildPublishPayload(catalog: LoadedCatalog): PublishPayload {
  return {
    body: catalog.rdf,
    contentType: catalog.contentType,
    sourceLabel: catalog.sourceLabel
  };
}

