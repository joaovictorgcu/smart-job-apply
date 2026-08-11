"""Every LinkedIn selector used by the automation layer, in one place.

This is the ONLY file that should need editing when LinkedIn changes its DOM.
Nothing here imports Playwright and nothing here holds state: the page objects in
`automation/linkedin/*` read these tuples, and `BrowserSession.find_first` tries
each candidate in order. LinkedIn ships A/B variants of the same screen to
different accounts, so every element is a tuple of fallbacks ordered from the
most semantic/stable (`role=`, `aria-label`, `data-*`) to the most brittle (deep
CSS). Never collapse a tuple to a single string.

Selector strings use Playwright's selector syntax, so `role=`, `text=`, `css=`
and `xpath=` engines are all valid entries.

Last verified against the LinkedIn web UI on 2026-08-11.
"""

from __future__ import annotations

from typing import Final


class Urls:
    """Stable LinkedIn entry points (path shapes change far less than markup)."""

    BASE: Final = "https://www.linkedin.com"
    FEED: Final = "https://www.linkedin.com/feed/"
    LOGIN: Final = "https://www.linkedin.com/login"
    JOB_SEARCH: Final = "https://www.linkedin.com/jobs/search/"
    JOB_VIEW: Final = "https://www.linkedin.com/jobs/view/{external_id}/"

    # Substrings that mean "we are not authenticated any more".
    LOGGED_OUT_FRAGMENTS: Final[tuple[str, ...]] = (
        "/login",
        "/uas/login",
        "/authwall",
        "/signup",
    )


class Auth:
    """Markers that tell a logged-in page from the login wall."""

    LOGGED_IN_MARKERS: Final[tuple[str, ...]] = (
        "css=.global-nav__me",
        'button[data-control-name="nav.settings"]',
        "css=img.global-nav__me-photo",
        'nav[aria-label="Primary Navigation"]',
        "css=.feed-identity-module",
        "css=.share-box-feed-entry__trigger",
    )

    LOGIN_FORM_MARKERS: Final[tuple[str, ...]] = (
        "css=form.login__form",
        "#username",
        "#session_key",
        'input[name="session_key"]',
    )

    # Shown by LinkedIn while a second factor is pending. Not a blocker: the human
    # is at the keyboard in the visible window and completes it themselves.
    TWO_FACTOR_MARKERS: Final[tuple[str, ...]] = (
        "#input__phone_verification_pin",
        'input[name="pin"]',
        "css=.two-step-verification",
    )

    DISPLAY_NAME: Final[tuple[str, ...]] = (
        "css=.global-nav__me-photo",
        "css=.feed-identity-module__actor-meta a",
        "css=.profile-rail-card__actor-link",
    )


class Search:
    """Job search results page."""

    RESULTS_CONTAINER: Final[tuple[str, ...]] = (
        "css=div.jobs-search-results-list",
        "css=.scaffold-layout__list > div",
        'div[data-results-list-top-scroll-sentinel] ~ ul',
        "css=ul.jobs-search__results-list",
    )

    JOB_CARD: Final[tuple[str, ...]] = (
        "css=li[data-occludable-job-id]",
        "css=div.job-card-container[data-job-id]",
        "css=li.jobs-search-results__list-item",
        "css=ul.jobs-search__results-list > li",
    )

    # Attributes carrying the numeric job id, checked in order on each card.
    CARD_ID_ATTRIBUTES: Final[tuple[str, ...]] = (
        "data-occludable-job-id",
        "data-job-id",
        "data-id",
    )

    CARD_LINK: Final[tuple[str, ...]] = (
        "css=a.job-card-container__link",
        "css=a.job-card-list__title",
        'a[href*="/jobs/view/"]',
    )

    CARD_TITLE: Final[tuple[str, ...]] = (
        "css=a.job-card-list__title strong",
        "css=a.job-card-list__title",
        "css=a.job-card-container__link",
        "css=.job-card-list__title--link",
        "css=h3.base-search-card__title",
    )

    CARD_COMPANY: Final[tuple[str, ...]] = (
        "css=.job-card-container__primary-description",
        "css=.artdeco-entity-lockup__subtitle",
        "css=.job-card-container__company-name",
        "css=h4.base-search-card__subtitle",
    )

    CARD_LOCATION: Final[tuple[str, ...]] = (
        "css=.job-card-container__metadata-item",
        "css=.artdeco-entity-lockup__caption",
        "css=.job-search-card__location",
    )

    CARD_POSTED_TIME: Final[tuple[str, ...]] = (
        "css=time",
        "css=.job-search-card__listdate",
        "css=.job-card-container__listed-time",
    )

    # "Applied" / "Application submitted" footer state on an already-used card.
    CARD_APPLIED_MARKER: Final[tuple[str, ...]] = (
        "css=.job-card-container__footer-job-state",
        "css=li.job-card-container__footer-item--highlighted",
        'text=/^(Applied|Candidatura enviada|Já se candidatou)/i',
    )

    CARD_EASY_APPLY_MARKER: Final[tuple[str, ...]] = (
        'text=/Easy Apply|Candidatura simplificada/i',
        "css=.job-card-container__apply-method",
    )

    NEXT_PAGE_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Next"i]',
        'button[aria-label="Next"]',
        "css=.artdeco-pagination__button--next",
    )

    NO_RESULTS: Final[tuple[str, ...]] = (
        "css=.jobs-search-no-results-banner",
        'text=/No matching jobs found|Nenhuma vaga encontrada/i',
    )

    # Text values LinkedIn uses to qualify the workplace arrangement on a card.
    REMOTE_TEXTS: Final[tuple[str, ...]] = ("remote", "remoto")
    HYBRID_TEXTS: Final[tuple[str, ...]] = ("hybrid", "híbrido", "hibrido")
    ONSITE_TEXTS: Final[tuple[str, ...]] = ("on-site", "onsite", "presencial")


class JobDetail:
    """Single job page (right pane or standalone /jobs/view/ page)."""

    TITLE: Final[tuple[str, ...]] = (
        "css=.job-details-jobs-unified-top-card__job-title",
        "css=h1.jobs-unified-top-card__job-title",
        "css=h1.top-card-layout__title",
        "css=h1",
    )

    COMPANY: Final[tuple[str, ...]] = (
        "css=.job-details-jobs-unified-top-card__company-name",
        "css=.jobs-unified-top-card__company-name",
        "css=a.topcard__org-name-link",
        "css=.topcard__flavor",
    )

    LOCATION: Final[tuple[str, ...]] = (
        "css=.job-details-jobs-unified-top-card__primary-description-container",
        "css=.jobs-unified-top-card__bullet",
        "css=.topcard__flavor--bullet",
    )

    DESCRIPTION: Final[tuple[str, ...]] = (
        "css=#job-details",
        "css=.jobs-description__content",
        "css=.jobs-box__html-content",
        "css=.show-more-less-html__markup",
    )

    SHOW_MORE_DESCRIPTION: Final[tuple[str, ...]] = (
        'role=button[name="Click to see more description"i]',
        'button[aria-label*="see more"]',
        "css=.show-more-less-html__button--more",
        'role=button[name="Ver mais"i]',
    )

    # Pills such as "Remote", "Hybrid", "Full-time" under the job title.
    WORKPLACE_PILLS: Final[tuple[str, ...]] = (
        "css=.job-details-jobs-unified-top-card__job-insight",
        "css=.jobs-unified-top-card__workplace-type",
        "css=.job-details-preferences-and-skills__pill",
        "css=.jobs-unified-top-card__job-insight span",
    )

    EASY_APPLY_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Easy Apply"i]',
        'button.jobs-apply-button[aria-label*="Easy Apply"]',
        'role=button[name="Candidatura simplificada"i]',
        "css=.jobs-apply-button--top-card button",
        "css=button.jobs-apply-button",
    )

    APPLIED_BANNER: Final[tuple[str, ...]] = (
        "css=.jobs-s-apply__application-submitted",
        "css=.artdeco-inline-feedback--success",
        'text=/Applied|Application submitted|Candidatura enviada/i',
    )

    POSTED_TIME: Final[tuple[str, ...]] = (
        "css=.jobs-unified-top-card__posted-date",
        "css=span.posted-time-ago__text",
        "css=.job-details-jobs-unified-top-card__primary-description-container time",
    )


class EasyApply:
    """The Easy Apply modal.

    `SUBMIT_BUTTON` is deliberately isolated from `NEXT_BUTTON`/`REVIEW_BUTTON`:
    the form-filling code only ever looks up the latter two, so a selector drift
    can never turn "advance one step" into "send the application".
    """

    MODAL: Final[tuple[str, ...]] = (
        'div[data-test-modal-id="easy-apply-modal"]',
        'role=dialog[name="Apply to"i]',
        "css=.jobs-easy-apply-modal",
        "css=div.artdeco-modal--layer-default",
    )

    MODAL_TITLE: Final[tuple[str, ...]] = (
        "css=.jobs-easy-apply-modal h2",
        "css=.artdeco-modal__header h2",
        "css=h2#jobs-apply-header",
    )

    FORM: Final[tuple[str, ...]] = (
        "css=form.jobs-easy-apply-form",
        'div[data-test-modal-id="easy-apply-modal"] form',
        "css=.artdeco-modal__content form",
        "css=form",
    )

    # Progress meter: read aria-valuenow / aria-valuemax, or value / max.
    PROGRESS: Final[tuple[str, ...]] = (
        "css=.artdeco-completeness-meter-linear__progress-element",
        'progress[aria-label*="progress"]',
        "css=progress",
        'div[role="progressbar"]',
    )

    # One wrapper per question. Radio/checkbox groups arrive as fieldsets.
    FORM_GROUPS: Final[tuple[str, ...]] = (
        'div[data-test-form-element]',
        "css=.jobs-easy-apply-form-section__grouping",
        "css=.fb-dash-form-element",
        "css=.jobs-easy-apply-form-element",
    )

    GROUP_LABEL: Final[tuple[str, ...]] = (
        "css=label",
        "css=legend span[aria-hidden='true']",
        "css=legend",
        "css=.fb-dash-form-element__label",
        "css=.artdeco-text-input--label",
    )

    TEXT_INPUT: Final[tuple[str, ...]] = (
        'input[type="text"]',
        'input[type="email"]',
        'input[type="tel"]',
        'input[type="url"]',
        "css=input.artdeco-text-input--input",
    )

    NUMBER_INPUT: Final[tuple[str, ...]] = (
        'input[type="number"]',
        'input[inputmode="numeric"]',
    )

    TEXTAREA: Final[tuple[str, ...]] = ("css=textarea",)

    SELECT: Final[tuple[str, ...]] = (
        "css=select",
        'div[data-test-text-entity-list-form-component] select',
    )

    RADIO_FIELDSET: Final[tuple[str, ...]] = (
        'fieldset[data-test-form-builder-radio-button-form-component]',
        "css=fieldset.jobs-easy-apply-form-element__fieldset",
        "css=fieldset",
    )

    RADIO_INPUT: Final[tuple[str, ...]] = ('input[type="radio"]',)

    CHECKBOX_INPUT: Final[tuple[str, ...]] = ('input[type="checkbox"]',)

    FILE_INPUT: Final[tuple[str, ...]] = (
        'input[type="file"]',
        'input[name="file"]',
        "css=.js-jobs-document-upload__input",
    )

    # Existing resume cards; used to tell "already attached" from "must upload".
    RESUME_CARD: Final[tuple[str, ...]] = (
        "css=.jobs-document-upload-redesign-card__container",
        "css=.jobs-resume-picker__resume",
        'div[data-test-jobs-document-upload-redesign-card]',
    )

    UPLOAD_RESUME_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Upload resume"i]',
        'label[for*="upload-resume"]',
        'role=button[name="Carregar currículo"i]',
    )

    # Cover-letter free-text box. Matched by label text, then by generic textarea.
    COVER_LETTER_LABELS: Final[tuple[str, ...]] = (
        "cover letter",
        "carta de apresentação",
        "carta de apresentacao",
        "message to the hiring manager",
        "mensagem",
        "additional information",
        "informações adicionais",
    )

    # Typeahead dropdown attached to city / school / company text inputs.
    TYPEAHEAD_CONTAINER: Final[tuple[str, ...]] = (
        "css=.basic-typeahead__triggered-content",
        'div[role="listbox"]',
        "css=.search-typeahead-v2__hit",
    )

    TYPEAHEAD_OPTION: Final[tuple[str, ...]] = (
        'div[role="option"]',
        "css=.basic-typeahead__selectable",
        "css=li",
    )

    NEXT_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Continue to next step"i]',
        'button[aria-label="Continue to next step"]',
        'role=button[name="Next"i]',
        'role=button[name="Avançar"i]',
        'button[data-easy-apply-next-button]',
    )

    REVIEW_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Review your application"i]',
        'button[aria-label="Review your application"]',
        'role=button[name="Review"i]',
        'role=button[name="Revisar"i]',
    )

    # ONLY `LinkedInBrowserService.submit()` may use this.
    SUBMIT_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Submit application"i]',
        'button[aria-label="Submit application"]',
        'role=button[name="Enviar candidatura"i]',
    )

    CLOSE_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Dismiss"i]',
        'button[aria-label="Dismiss"]',
        "css=.artdeco-modal__dismiss",
        'role=button[name="Fechar"i]',
    )

    DISCARD_BUTTON: Final[tuple[str, ...]] = (
        'role=button[name="Discard"i]',
        'button[data-control-name="discard_application_confirm_btn"]',
        'role=button[name="Descartar"i]',
    )

    # Post-submit confirmation ("Your application was sent to ...").
    SUBMIT_CONFIRMATION: Final[tuple[str, ...]] = (
        "css=.jobs-easy-apply-confirmation",
        'text=/Your application was sent|Sua candidatura foi enviada/i',
        "css=.artdeco-modal__content .jobs-post-apply-confirmation",
    )

    VALIDATION_ERROR: Final[tuple[str, ...]] = (
        "css=.artdeco-inline-feedback--error",
        'div[data-test-form-element-error-messages]',
        "css=.fb-dash-form-element__error-text",
    )

    REQUIRED_MARKER: Final[tuple[str, ...]] = (
        'span[aria-hidden="true"]:text("*")',
        "css=.fb-dash-form-element__label-title--is-required",
    )

    # Opt-outs LinkedIn pre-checks for the user; we never touch them.
    FOLLOW_COMPANY_CHECKBOX: Final[tuple[str, ...]] = (
        "#follow-company-checkbox",
        'input[id*="follow-company"]',
    )


class Checkpoint:
    """CAPTCHA / security-verification detection.

    Detection is intentionally broad and one-way: anything matching here stops
    the run with `SecurityCheckpointError`. We never attempt to solve, click
    through, or otherwise bypass a challenge.
    """

    URL_FRAGMENTS: Final[tuple[str, ...]] = (
        "/checkpoint/",
        "/challenge",
        "captcha",
        "/uas/consumer-email-challenge",
    )

    ELEMENTS: Final[tuple[str, ...]] = (
        'iframe[title*="challenge"]',
        "#captcha-internal",
        'iframe[src*="captcha"]',
        'div[data-test-id="challenge"]',
        "css=.challenge-dialog",
        "#recaptcha-verify-button",
    )

    # Lower-cased substrings looked up in the page body text.
    TEXT_MARKERS: Final[tuple[str, ...]] = (
        "security verification",
        "unusual activity",
        "let's do a quick security check",
        "verify you're a human",
        "we've restricted your account",
        "suspicious activity",
        "verificação de segurança",
        "verificacao de seguranca",
        "atividade incomum",
        "atividade suspeita",
        "verifique se você é humano",
        "sua conta foi restringida",
    )
