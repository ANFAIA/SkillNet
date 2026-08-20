import type {
  ComponentFamily,
  ComponentRole,
  LearnerActionFacet,
  LearningContextFacet,
  LearningPurposeFacet,
  RepresentationFacet,
  SubjectFacet,
} from "./taxonomy";

export type LocalizedText = string | Readonly<Record<string, string>>;

export type ConditionOperator =
  | "equals"
  | "not-equals"
  | "contains"
  | "not-contains"
  | "greater-than"
  | "less-than"
  | "is-set"
  | "is-not-set";

export interface AuthoringCondition {
  readonly path: string;
  readonly operator: ConditionOperator;
  readonly value?: string | number | boolean | readonly (string | number)[];
}

export type RequirednessLevel = "required" | "progressive" | "optional";

export interface ConditionalRequiredness {
  readonly level: RequirednessLevel;
  readonly when: AuthoringCondition;
}

/**
 * `true` and a bare condition are retained for backwards compatibility: they mean "required"
 * always and "required when the condition matches", respectively.
 */
export type Requiredness =
  | boolean
  | RequirednessLevel
  | AuthoringCondition
  | ConditionalRequiredness;

export interface AuthoringOption {
  readonly value: string;
  readonly label: LocalizedText;
  readonly description?: LocalizedText;
}

interface AuthoringFieldBase {
  readonly key: string;
  readonly label: LocalizedText;
  readonly description?: LocalizedText;
  readonly required?: Requiredness;
  readonly visibleWhen?: AuthoringCondition;
  readonly defaultValue?: unknown;
  readonly i18n?: boolean;
  readonly group?: string;
}

export interface TextAuthoringField extends AuthoringFieldBase {
  readonly kind: "text" | "rich-text";
  readonly minLength?: number;
  readonly maxLength?: number;
  readonly pattern?: string;
  readonly multiline?: boolean;
}

export interface NumberAuthoringField extends AuthoringFieldBase {
  readonly kind: "number";
  readonly min?: number;
  readonly max?: number;
  readonly step?: number;
  readonly unit?: LocalizedText;
}

export interface BooleanAuthoringField extends AuthoringFieldBase {
  readonly kind: "boolean";
}

export interface ChoiceAuthoringField extends AuthoringFieldBase {
  readonly kind: "select" | "multi-select";
  readonly options: readonly AuthoringOption[];
}

export interface AssetAuthoringField extends AuthoringFieldBase {
  readonly kind: "asset";
  readonly accept?: readonly string[];
  readonly altTextField?: string;
}

export interface ObjectAuthoringField extends AuthoringFieldBase {
  readonly kind: "object";
  readonly fields: readonly AuthoringField[];
}

export interface ListAuthoringField extends AuthoringFieldBase {
  readonly kind: "list";
  readonly item: AuthoringField;
  readonly minItems?: number;
  readonly maxItems?: number;
  readonly reorderable?: boolean;
}

export type AuthoringField =
  | TextAuthoringField
  | NumberAuthoringField
  | BooleanAuthoringField
  | ChoiceAuthoringField
  | AssetAuthoringField
  | ObjectAuthoringField
  | ListAuthoringField;

export interface AuthoringSchema {
  readonly version: string;
  readonly fields: readonly AuthoringField[];
  readonly supportsLocalization?: boolean;
}

export type EvidenceStrength = "high" | "moderate" | "low" | "not-evaluated";

export interface EvidenceReference {
  readonly id: string;
  readonly strength: EvidenceStrength;
  readonly citation: string;
  readonly url?: string;
  readonly claim: string;
  readonly limitations?: string;
}

export interface AccessibilityMetadata {
  readonly keyboard: "full" | "alternative" | "not-applicable" | "unsupported";
  readonly screenReader: "full" | "partial" | "not-applicable" | "unsupported";
  readonly draggingAlternative?: boolean;
  readonly requiresAltText?: boolean;
  readonly captions?: "required" | "recommended" | "not-applicable";
  readonly wcagCriteria?: readonly string[];
  readonly notes?: string;
}

export interface QtiMapping {
  readonly interaction: string;
  readonly fidelity: "exact" | "approximate" | "none";
  readonly version?: "3.0";
  readonly notes?: string;
}

export interface XapiMapping {
  readonly interactionType?:
    | "true-false"
    | "choice"
    | "fill-in"
    | "long-fill-in"
    | "matching"
    | "performance"
    | "sequencing"
    | "likert"
    | "numeric"
    | "other";
  readonly verbs?: readonly string[];
  readonly notes?: string;
}

export interface InteroperabilityMappings {
  readonly qti?: QtiMapping | readonly QtiMapping[];
  readonly xapi?: XapiMapping | readonly XapiMapping[];
}

export interface OptionalDependency {
  readonly package: string;
  readonly purpose: string;
  readonly requiredFor?: readonly string[];
  readonly fallback?: string;
}

export interface MigrationMetadata {
  readonly from: string;
  readonly to: string;
  readonly description: string;
  readonly breaking?: boolean;
}

export interface VersionMetadata {
  readonly schema: string;
  readonly component: string;
  readonly migrations?: readonly MigrationMetadata[];
}

export interface CatalogLifecycle {
  readonly availability: "available" | "planned" | "deprecated";
  readonly maturity: "draft" | "experimental" | "stable";
}

export interface ComponentVariant {
  readonly id: string;
  readonly name: LocalizedText;
  readonly description?: LocalizedText;
  readonly availability?: CatalogLifecycle["availability"];
}

export interface ComponentFacets {
  readonly subjects: readonly SubjectFacet[];
  readonly representations: readonly RepresentationFacet[];
  readonly learnerActions: readonly LearnerActionFacet[];
  readonly purposes: readonly LearningPurposeFacet[];
  readonly contexts?: readonly LearningContextFacet[];
}

export interface ComponentManifest {
  readonly id: string;
  readonly name: LocalizedText;
  readonly description: LocalizedText;
  readonly role: ComponentRole;
  readonly families: readonly ComponentFamily[];
  readonly facets: ComponentFacets;
  readonly lifecycle: CatalogLifecycle;
  readonly version: VersionMetadata;
  readonly authoring: AuthoringSchema;
  readonly evidence: readonly EvidenceReference[];
  readonly accessibility: AccessibilityMetadata;
  readonly mappings?: InteroperabilityMappings;
  readonly variants?: readonly ComponentVariant[];
  readonly optionalDependencies?: readonly OptionalDependency[];
  readonly capabilities?: readonly string[];
  readonly tags?: readonly string[];
}

export type CatalogCollectionKind = "foundation" | "subject" | "context" | "experience";
export type CatalogCollectionStatus = "draft" | "available" | "deprecated";
export type CollectionItemRole = "required" | "recommended" | "optional";

export interface CollectionItem {
  readonly manifestId: string;
  readonly typeId?: string;
  readonly role: CollectionItemRole;
  readonly reason: string;
}

export interface CatalogCollectionKit {
  readonly name: string;
  readonly includeRoles: readonly CollectionItemRole[];
}

export interface CatalogCollection {
  readonly id: string;
  readonly version: string;
  readonly slug: string;
  readonly title: LocalizedText;
  readonly description: LocalizedText;
  readonly kind: CatalogCollectionKind;
  readonly status: CatalogCollectionStatus;
  readonly facets?: Partial<ComponentFacets>;
  readonly items: readonly CollectionItem[];
  readonly kit?: CatalogCollectionKit;
  readonly tags?: readonly string[];
}

export type ResponseStatus = "draft" | "streaming" | "submitted";

interface ResponseBase {
  readonly id: string;
  readonly componentId: string;
  readonly status: ResponseStatus;
  readonly answeredAt?: string;
  readonly durationMs?: number;
}

export type Response = ResponseBase &
  (
    | { readonly kind: "choice"; readonly value: readonly string[] }
    | { readonly kind: "text"; readonly value: string }
    | { readonly kind: "numeric"; readonly value: number; readonly unit?: string }
    | { readonly kind: "boolean"; readonly value: boolean }
    | { readonly kind: "ordering"; readonly value: readonly string[] }
    | { readonly kind: "matching"; readonly value: Readonly<Record<string, string | readonly string[]>> }
    | { readonly kind: "points"; readonly value: readonly { readonly x: number; readonly y: number }[] }
    | { readonly kind: "file" | "audio" | "drawing"; readonly value: string }
    | { readonly kind: "composite"; readonly value: readonly Response[] }
  );

export interface Feedback {
  readonly kind: "informative" | "corrective" | "hint" | "explanation" | "model-answer";
  readonly message: LocalizedText;
  readonly target?: string;
  readonly priority?: "primary" | "secondary";
}

export interface Result {
  readonly responseId: string;
  readonly status: "ungraded" | "correct" | "incorrect" | "partial";
  readonly score?: number;
  readonly maxScore?: number;
  readonly normalizedScore?: number;
  readonly feedback?: readonly Feedback[];
  readonly outcomes?: Readonly<Record<string, string | number | boolean>>;
  readonly evaluatedAt?: string;
}

export interface ValidationIssue {
  readonly path: string;
  readonly code: string;
  readonly message: string;
  readonly severity: "error" | "warning";
}

export interface AuthoringValidationOptions {
  readonly mode: "complete" | "streaming";
}

export type ValidationResult<T> =
  | { readonly success: true; readonly data: T; readonly issues: readonly ValidationIssue[] }
  | { readonly success: false; readonly issues: readonly ValidationIssue[] };
