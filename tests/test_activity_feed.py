import datetime as dt
from denguesux.activity_feed import filter_items,parse_rss,data_events
NOW=dt.datetime(2026,10,10,tzinfo=dt.timezone.utc)

def item(title='Singapore dengue update',url='https://www.channelnewsasia.com/singapore/dengue-123',**extra):
    return {'title':title,'url':url,'source':'CNA','published_at':'2026-10-09T00:00:00Z',**extra}

def test_allowlist_topic_singapore_and_dates_are_all_required():
    good=item()
    rows=[good,item('Singapore election news'),item('Florida dengue surge'),item(url='https://evil.example/singapore/dengue'),item('Dengue rises worldwide',url='https://www.channelnewsasia.com/world/dengue'),item(published_at=None),item(published_at='2026-10-11T00:00:00Z')]
    assert filter_items(rows,NOW)==filter_items([good],NOW)

def test_url_deduplication_and_metadata_only():
    rows=[item(description='NEVER STORE',article_body='NEVER STORE'),item(url='https://www.channelnewsasia.com/singapore/dengue-123?utm_source=x')]
    result=filter_items(rows,NOW)
    assert len(result)==1
    assert set(result[0])=={'title','source','url','published_at','kind'}

def test_rss_description_does_not_make_irrelevant_title_match():
    rss=b'<rss><channel><item><title>Singapore politics</title><link>https://www.channelnewsasia.com/singapore/politics</link><description>Dengue mosquitoes</description><pubDate>Fri, 09 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>'
    assert filter_items(parse_rss(rss,'CNA'),NOW)==[]

def test_growth_under_five_excluded_and_comparison_date_preserved():
    d={'current':{'as_of':'2026-10-10T00:00:00Z'},'growth':{'changes':{'from_date':'2026-09-24','items':[{'kind':'Growing','change':3},{'kind':'Growing','change':5}]}}}
    rows=data_events(d)
    assert len(rows)==1 and rows[0]['comparison_from']=='2026-09-24'
