from django.test import TestCase
from django.contrib.auth.models import Group

from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Contribution
from evap.rewards.models import RewardPointGranting, RewardPointRedemption
from evap.staff.tools import merge_users


class MergeUsersTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user1 = mommy.make(UserProfile, username="test1")
        cls.user2 = mommy.make(UserProfile, username="test2")
        cls.user3 = mommy.make(UserProfile, username="test3")
        cls.group1 = mommy.make(Group, name="group1")
        cls.group2 = mommy.make(Group, name="group2")
        cls.main_user = mommy.make(UserProfile,
            username="main_user",
            title="Dr.",
            first_name="Main",
            last_name="",
            email="",  # test that merging works when taking the email from other user (UniqueConstraint)
            groups=[cls.group1],
            delegates=[cls.user1, cls.user2],
            represented_users=[cls.user3],
            cc_users=[cls.user1],
            ccing_users=[]
        )
        cls.other_user = mommy.make(UserProfile,
            username="other_user",
            title="",
            first_name="Other",
            last_name="User",
            email="other@test.com",
            groups=[cls.group2],
            delegates=[cls.user3],
            represented_users=[cls.user1],
            cc_users=[],
            ccing_users=[cls.user1, cls.user2],
            is_superuser=True
        )
        cls.course1 = mommy.make(Course, name="course1", participants=[cls.main_user, cls.other_user])  # this should make the merge fail
        cls.course2 = mommy.make(Course, name="course2", participants=[cls.main_user], voters=[cls.main_user])
        cls.course3 = mommy.make(Course, name="course3", participants=[cls.other_user], voters=[cls.other_user])
        cls.contribution1 = mommy.make(Contribution, contributor=cls.main_user, course=cls.course1)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.other_user, course=cls.course1)  # this should make the merge fail
        cls.contribution3 = mommy.make(Contribution, contributor=cls.other_user, course=cls.course2)
        cls.rewardpointgranting_main = mommy.make(RewardPointGranting, user_profile=cls.main_user)
        cls.rewardpointgranting_other = mommy.make(RewardPointGranting, user_profile=cls.other_user)
        cls.rewardpointredemption_main = mommy.make(RewardPointRedemption, user_profile=cls.main_user)
        cls.rewardpointredemption_other = mommy.make(RewardPointRedemption, user_profile=cls.other_user)

    def test_merge_handles_all_attributes(self):
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)

        all_attrs = list(field.name for field in UserProfile._meta.get_fields(include_hidden=True))

        # these are relations to intermediate models generated by django for m2m relations.
        # we can safely ignore these since the "normal" fields of the m2m relations are present as well.
        all_attrs = list(attr for attr in all_attrs if not attr.startswith("UserProfile_"))

        # equally named fields are not supported, sorry
        self.assertEqual(len(all_attrs), len(set(all_attrs)))

        # some attributes we don't care about when merging
        ignored_attrs = {
            'id',  # nothing to merge here
            'password',  # not used in production
            'last_login',  # something to really not care about
            'user_permissions',  # we don't use permissions
            'logentry',  # wtf
            'login_key',  # we decided to discard other_user's login key
            'login_key_valid_until',  # not worth dealing with
            'Course_voters+',  # some more intermediate models, for an explanation see above
            'Course_participants+',  # intermediate model
        }
        expected_attrs = set(all_attrs) - ignored_attrs

        # actual merge happens here
        merged_user, errors, warnings = merge_users(user1, user2)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        handled_attrs = set(merged_user.keys())

        # attributes that are handled in the merge method but that are not present in the merged_user dict
        # add attributes here only if you're actually dealing with them in merge_users().
        additional_handled_attrs = {
            'grades_last_modified_user+',
            'course_last_modified_user+',
        }

        actual_attrs = handled_attrs | additional_handled_attrs

        self.assertEqual(expected_attrs, actual_attrs)

    def test_merge_users(self):
        __, errors, warnings = merge_users(self.main_user, self.other_user)  # merge should fail
        self.assertSequenceEqual(errors, ['contributions', 'courses_participating_in'])
        self.assertSequenceEqual(warnings, ['rewards'])

        # assert that nothing has changed
        self.main_user.refresh_from_db()
        self.other_user.refresh_from_db()
        self.assertEqual(self.main_user.username, "main_user")
        self.assertEqual(self.main_user.title, "Dr.")
        self.assertEqual(self.main_user.first_name, "Main")
        self.assertEqual(self.main_user.last_name, "")
        self.assertEqual(self.main_user.email, "")
        self.assertSequenceEqual(self.main_user.groups.all(), [self.group1])
        self.assertSequenceEqual(self.main_user.delegates.all(), [self.user1, self.user2])
        self.assertSequenceEqual(self.main_user.represented_users.all(), [self.user3])
        self.assertSequenceEqual(self.main_user.cc_users.all(), [self.user1])
        self.assertSequenceEqual(self.main_user.ccing_users.all(), [])
        self.assertFalse(self.main_user.is_superuser)
        self.assertTrue(RewardPointGranting.objects.filter(user_profile=self.main_user).exists())
        self.assertTrue(RewardPointRedemption.objects.filter(user_profile=self.main_user).exists())
        self.assertEqual(self.other_user.username, "other_user")
        self.assertEqual(self.other_user.title, "")
        self.assertEqual(self.other_user.first_name, "Other")
        self.assertEqual(self.other_user.last_name, "User")
        self.assertEqual(self.other_user.email, "other@test.com")
        self.assertSequenceEqual(self.other_user.groups.all(), [self.group2])
        self.assertSequenceEqual(self.other_user.delegates.all(), [self.user3])
        self.assertSequenceEqual(self.other_user.represented_users.all(), [self.user1])
        self.assertSequenceEqual(self.other_user.cc_users.all(), [])
        self.assertSequenceEqual(self.other_user.ccing_users.all(), [self.user1, self.user2])
        self.assertSequenceEqual(self.course1.participants.all(), [self.main_user, self.other_user])
        self.assertSequenceEqual(self.course2.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course2.voters.all(), [self.main_user])
        self.assertSequenceEqual(self.course3.participants.all(), [self.other_user])
        self.assertSequenceEqual(self.course3.voters.all(), [self.other_user])
        self.assertTrue(RewardPointGranting.objects.filter(user_profile=self.other_user).exists())
        self.assertTrue(RewardPointRedemption.objects.filter(user_profile=self.other_user).exists())

        # fix data
        self.course1.participants = [self.main_user]
        self.contribution2.delete()

        __, errors, warnings = merge_users(self.main_user, self.other_user)  # merge should succeed
        self.assertEqual(errors, [])
        self.assertSequenceEqual(warnings, ['rewards']) # rewards warning is still there

        self.main_user.refresh_from_db()
        self.assertEqual(self.main_user.username, "main_user")
        self.assertEqual(self.main_user.title, "Dr.")
        self.assertEqual(self.main_user.first_name, "Main")
        self.assertEqual(self.main_user.last_name, "User")
        self.assertEqual(self.main_user.email, "other@test.com")
        self.assertSequenceEqual(self.main_user.groups.all(), [self.group1, self.group2])
        self.assertSequenceEqual(self.main_user.delegates.all(), [self.user1, self.user2, self.user3])
        self.assertSequenceEqual(self.main_user.represented_users.all(), [self.user1, self.user3])
        self.assertSequenceEqual(self.main_user.cc_users.all(), [self.user1])
        self.assertSequenceEqual(self.main_user.ccing_users.all(), [self.user1, self.user2])
        self.assertSequenceEqual(self.course1.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course2.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course2.voters.all(), [self.main_user])
        self.assertSequenceEqual(self.course3.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course3.voters.all(), [self.main_user])
        self.assertTrue(self.main_user.is_superuser)
        self.assertTrue(RewardPointGranting.objects.filter(user_profile=self.main_user).exists())
        self.assertTrue(RewardPointRedemption.objects.filter(user_profile=self.main_user).exists())
        self.assertFalse(RewardPointGranting.objects.filter(user_profile=self.other_user).exists())
        self.assertFalse(RewardPointRedemption.objects.filter(user_profile=self.other_user).exists())
