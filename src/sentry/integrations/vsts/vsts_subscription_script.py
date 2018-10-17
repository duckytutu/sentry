from __future__ import absolute_import

import logging

from django.core.urlresolvers import reverse
from uuid import uuid4

from sentry.constants import ObjectStatus
from sentry.integrations.exceptions import ApiError, ApiUnauthorized
from sentry.models import OrganizationIntegration
from sentry.utils.http import absolute_uri

VSTS_WEBHOOK_URL = absolute_uri(reverse('sentry-extensions-vsts-issue-updated'))

logger = logging.getLogger('sentry.integrations.vsts_script')


def create_webhook(integration, organization_id):
    installation = integration.get_installation(organization_id)
    client = installation.get_client()
    shared_secret = uuid4.hex + uuid4.hex

    resp = client.create_subscription(
        instance=installation.instance,
        shared_secret=shared_secret,
    )

    installation.model.metadata['subscription'] = {
        'id': resp['id'],
        'secret': shared_secret,
    }
    installation.model.save()


def recreate_subscriptions(self):
    org_integrations = OrganizationIntegration.objects.filter(
        integration__provider='vsts',
        integration__status=ObjectStatus.VISIBLE,
        status=ObjectStatus.VISIBLE,
    ).select_related('integration')

    # TODO(lb): this looks a little weird to me...
    # can I run into issues with both values_list and distinct?
    integration_ids = list(
        org_integrations.values_list('integration_id', flat=True).distinct('integration_id')
    )

    for org_integration in org_integrations:
        # The integration associated with the organizationintegration
        # has successfully had its subscription re-created; skip it.
        integration = org_integration.integration
        if integration.id not in integration_ids:
            continue

        integration_ids.remove(integration.id)

        try:
            create_webhook(integration, org_integration.organization_id)
        except (ApiError, ApiUnauthorized):
            # potentially try the integration again with another org (if it exists)
            integration_ids.append(integration.id)

    logger.info(
        'Was unable to re-create subscription',
        extra={
            'integrations': integration_ids,
        }
    )
